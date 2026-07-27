"""Strict, fingerprint-bound manual image review plans."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from privacylens.models import BoundingBox, Detection

REVIEW_PLAN_SCHEMA_VERSION = "1.0"
MAX_REVIEW_PLAN_BYTES = 64 * 1024
MAX_REVIEW_REGIONS = 1000
KIND_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,31}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    """Human-approved regions bound to one exact source file."""

    input_sha256: str
    detections: tuple[Detection, ...]

    def __post_init__(self) -> None:
        if not SHA256_PATTERN.fullmatch(self.input_sha256):
            raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.detections, tuple):
            raise ValueError("review plan detections must be an immutable tuple")
        if len(self.detections) > MAX_REVIEW_REGIONS:
            raise ValueError(f"review plan exceeds the {MAX_REVIEW_REGIONS}-region limit")
        for detection in self.detections:
            _validate_detection(detection)
        if len(set(self.detections)) != len(self.detections):
            raise ValueError("review plan regions must not contain duplicates")

    def validate_for_image(self, *, width: int, height: int) -> None:
        """Reject regions that do not fit the source image exactly."""

        for detection in self.detections:
            if detection.box.x2 > width or detection.box.y2 > height:
                raise ValueError("review plan region is outside the source image")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": REVIEW_PLAN_SCHEMA_VERSION,
            "input_sha256": self.input_sha256,
            "regions": [
                {"kind": detection.kind, "box": detection.box.as_list()}
                for detection in self.detections
            ],
        }


def load_review_plan(path: str | Path) -> ReviewPlan:
    """Load a small review plan without accepting silent schema changes."""

    review_path = Path(path)
    if not review_path.is_file():
        raise FileNotFoundError(f"review plan does not exist: {review_path.name}")
    if review_path.suffix.lower() != ".json":
        raise ValueError("review plan must use the .json extension")
    if review_path.stat().st_size > MAX_REVIEW_PLAN_BYTES:
        raise ValueError(f"review plan exceeds the {MAX_REVIEW_PLAN_BYTES}-byte safety limit")

    data = _read_json(review_path)
    allowed_keys = {"schema_version", "input_sha256", "regions"}
    unknown_keys = set(data) - allowed_keys
    if unknown_keys:
        raise ValueError(f"unknown review-plan key: {sorted(unknown_keys)[0]}")
    if data.get("schema_version") != REVIEW_PLAN_SCHEMA_VERSION:
        raise ValueError(f"review plan schema_version must be {REVIEW_PLAN_SCHEMA_VERSION}")
    input_sha256 = data.get("input_sha256")
    if not isinstance(input_sha256, str):
        raise ValueError("review plan input_sha256 must be a string")

    raw_regions = data.get("regions")
    if not isinstance(raw_regions, list):
        raise ValueError("review plan regions must be a list")
    if len(raw_regions) > MAX_REVIEW_REGIONS:
        raise ValueError(f"review plan exceeds the {MAX_REVIEW_REGIONS}-region limit")
    detections = tuple(_parse_region(region) for region in raw_regions)
    return ReviewPlan(input_sha256=input_sha256, detections=detections)


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw_data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"review plan is not valid UTF-8: {path.name}") from error
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as error:
        raise ValueError(f"review plan is not valid JSON: {path.name}") from error
    if not isinstance(data, dict):
        raise ValueError("review plan JSON must contain an object")
    return data


def _parse_region(value: object) -> Detection:
    if not isinstance(value, dict):
        raise ValueError("each review-plan region must be an object")
    unknown_keys = set(value) - {"kind", "box"}
    if unknown_keys:
        raise ValueError(f"unknown review-region key: {sorted(unknown_keys)[0]}")
    if set(value) != {"kind", "box"}:
        raise ValueError("each review-plan region requires kind and box")

    kind = value["kind"]
    if not isinstance(kind, str) or not KIND_PATTERN.fullmatch(kind):
        raise ValueError("review-region kind must use lowercase letters, digits, _ or -")

    raw_box = value["box"]
    if (
        not isinstance(raw_box, list)
        or len(raw_box) != 4
        or any(
            isinstance(coordinate, bool) or not isinstance(coordinate, int)
            for coordinate in raw_box
        )
    ):
        raise ValueError("review-region box must contain four integer coordinates")
    x1, y1, x2, y2 = raw_box
    if min(raw_box) < 0 or x2 <= x1 or y2 <= y1:
        raise ValueError("review-region box must be non-empty and non-negative")
    return Detection(kind=kind, box=BoundingBox(x1, y1, x2, y2), score=None)


def _validate_detection(detection: Detection) -> None:
    if not isinstance(detection, Detection):
        raise ValueError("review plan detections must use Detection objects")
    if not KIND_PATTERN.fullmatch(detection.kind):
        raise ValueError("review-region kind must use lowercase letters, digits, _ or -")
    if detection.score is not None:
        raise ValueError("manual review regions must not claim a model score")
    if not isinstance(detection.box, BoundingBox):
        raise ValueError("review-region box must use BoundingBox")
    coordinates = detection.box.as_list()
    if any(
        isinstance(coordinate, bool) or not isinstance(coordinate, int)
        for coordinate in coordinates
    ):
        raise ValueError("review-region box must contain four integer coordinates")
    if (
        min(coordinates) < 0
        or detection.box.x2 <= detection.box.x1
        or detection.box.y2 <= detection.box.y1
    ):
        raise ValueError("review-region box must be non-empty and non-negative")
