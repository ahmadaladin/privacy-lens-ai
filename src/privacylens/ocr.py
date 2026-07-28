"""Strict OCR observation contract and PII-to-image region mapping."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from privacylens.models import BoundingBox, Detection
from privacylens.text_recognition import CompositeTextRecognizer, TextRecognizer

OCR_SIDECAR_SCHEMA_VERSION = "1.0"
MAX_OCR_SIDECAR_BYTES = 256 * 1024
MAX_OCR_OBSERVATIONS = 5000
MAX_OCR_TEXT_CHARACTERS = 4096
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class OCRObservation:
    """Text and image coordinates produced by an upstream OCR engine."""

    text: str
    box: BoundingBox
    score: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("OCR observation text must be a non-empty string")
        if len(self.text) > MAX_OCR_TEXT_CHARACTERS:
            raise ValueError(
                f"OCR observation text exceeds the {MAX_OCR_TEXT_CHARACTERS}-character limit"
            )
        if "\x00" in self.text:
            raise ValueError("OCR observation text must not contain NUL characters")
        _validate_box(self.box)
        if self.score is not None and (
            isinstance(self.score, bool)
            or not isinstance(self.score, (int, float))
            or not math.isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise ValueError("OCR observation score must be null or between 0 and 1")

    def to_sensitive_dict(self) -> dict[str, object]:
        """Serialize the observation for a protected sidecar, including raw text."""

        return {
            "text": self.text,
            "box": self.box.as_list(),
            "score": None if self.score is None else round(float(self.score), 4),
        }


@dataclass(frozen=True, slots=True)
class OCRSidecar:
    """OCR observations bound to the exact image from which they were extracted."""

    input_sha256: str
    observations: tuple[OCRObservation, ...]

    def __post_init__(self) -> None:
        if not SHA256_PATTERN.fullmatch(self.input_sha256):
            raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.observations, tuple):
            raise ValueError("OCR observations must be an immutable tuple")
        if len(self.observations) > MAX_OCR_OBSERVATIONS:
            raise ValueError(f"OCR sidecar exceeds the {MAX_OCR_OBSERVATIONS}-observation limit")
        for observation in self.observations:
            if not isinstance(observation, OCRObservation):
                raise ValueError("OCR sidecar observations must use OCRObservation objects")
        if len(set(self.observations)) != len(self.observations):
            raise ValueError("OCR sidecar observations must not contain duplicates")

    def validate_for_image(self, *, width: int, height: int) -> None:
        """Reject observations that do not fit the bound source image."""

        for observation in self.observations:
            if observation.box.x2 > width or observation.box.y2 > height:
                raise ValueError("OCR observation is outside the source image")

    def pii_detections(
        self,
        *,
        recognizer: TextRecognizer | None = None,
    ) -> tuple[Detection, ...]:
        """Map OCR observations containing supported PII to image regions."""

        active_recognizer = recognizer or CompositeTextRecognizer()
        unique: dict[tuple[str, BoundingBox], Detection] = {}
        for observation in self.observations:
            kinds = sorted(
                {detection.kind for detection in active_recognizer.detect(observation.text)}
            )
            if not kinds:
                continue
            kind = "_".join(kinds)
            detection = Detection(kind=kind, box=observation.box, score=None)
            unique[(kind, observation.box)] = detection
        return tuple(unique.values())

    def to_sensitive_dict(self) -> dict[str, object]:
        """Serialize a protected OCR sidecar; never use this as an audit record."""

        return {
            "schema_version": OCR_SIDECAR_SCHEMA_VERSION,
            "input_sha256": self.input_sha256,
            "observations": [observation.to_sensitive_dict() for observation in self.observations],
        }


def load_ocr_sidecar(path: str | Path) -> OCRSidecar:
    """Load a bounded, versioned OCR sidecar without echoing its raw text."""

    sidecar_path = Path(path)
    if not sidecar_path.is_file():
        raise FileNotFoundError(f"OCR sidecar does not exist: {sidecar_path.name}")
    if sidecar_path.suffix.lower() != ".json":
        raise ValueError("OCR sidecar must use the .json extension")
    if sidecar_path.stat().st_size > MAX_OCR_SIDECAR_BYTES:
        raise ValueError(f"OCR sidecar exceeds the {MAX_OCR_SIDECAR_BYTES}-byte safety limit")

    data = _read_json(sidecar_path)
    allowed_keys = {"schema_version", "input_sha256", "observations"}
    unknown_keys = set(data) - allowed_keys
    if unknown_keys:
        raise ValueError(f"unknown OCR-sidecar key: {sorted(unknown_keys)[0]}")
    if data.get("schema_version") != OCR_SIDECAR_SCHEMA_VERSION:
        raise ValueError(f"OCR sidecar schema_version must be {OCR_SIDECAR_SCHEMA_VERSION}")
    input_sha256 = data.get("input_sha256")
    if not isinstance(input_sha256, str):
        raise ValueError("OCR sidecar input_sha256 must be a string")
    raw_observations = data.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("OCR sidecar observations must be a list")
    if len(raw_observations) > MAX_OCR_OBSERVATIONS:
        raise ValueError(f"OCR sidecar exceeds the {MAX_OCR_OBSERVATIONS}-observation limit")
    return OCRSidecar(
        input_sha256=input_sha256,
        observations=tuple(_parse_observation(value) for value in raw_observations),
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw_data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"OCR sidecar is not valid UTF-8: {path.name}") from error
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as error:
        raise ValueError(f"OCR sidecar is not valid JSON: {path.name}") from error
    if not isinstance(data, dict):
        raise ValueError("OCR sidecar JSON must contain an object")
    return data


def _parse_observation(value: object) -> OCRObservation:
    if not isinstance(value, dict):
        raise ValueError("each OCR observation must be an object")
    unknown_keys = set(value) - {"text", "box", "score"}
    if unknown_keys:
        raise ValueError(f"unknown OCR-observation key: {sorted(unknown_keys)[0]}")
    if set(value) != {"text", "box", "score"}:
        raise ValueError("each OCR observation requires text, box, and score")
    raw_box = value["box"]
    if (
        not isinstance(raw_box, list)
        or len(raw_box) != 4
        or any(
            isinstance(coordinate, bool) or not isinstance(coordinate, int)
            for coordinate in raw_box
        )
    ):
        raise ValueError("OCR observation box must contain four integer coordinates")
    x1, y1, x2, y2 = raw_box
    return OCRObservation(
        text=value["text"],  # type: ignore[arg-type]
        box=BoundingBox(x1, y1, x2, y2),
        score=value["score"],  # type: ignore[arg-type]
    )


def _validate_box(box: BoundingBox) -> None:
    if not isinstance(box, BoundingBox):
        raise ValueError("OCR observation box must use BoundingBox")
    coordinates = box.as_list()
    if any(
        isinstance(coordinate, bool) or not isinstance(coordinate, int)
        for coordinate in coordinates
    ):
        raise ValueError("OCR observation box must contain four integer coordinates")
    if min(coordinates) < 0 or box.is_empty:
        raise ValueError("OCR observation box must be non-empty and non-negative")
