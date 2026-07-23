"""End-to-end image processing and audit reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from privacylens.detectors.base import Detector
from privacylens.detectors.haar_face import HaarFaceDetector
from privacylens.models import Detection
from privacylens.redaction import redact_regions

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}
MANIFEST_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    input_path: Path
    output_path: Path
    style: str
    detector: str
    detections: tuple[Detection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "style": self.style,
            "detector": self.detector,
            "detections": [detection.to_dict() for detection in self.detections],
        }

    def write_manifest(self, path: str | Path) -> None:
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def process_image(
    input_path: str | Path,
    output_path: str | Path,
    *,
    style: str = "blur",
    detector: Detector | None = None,
) -> ProcessResult:
    """Detect and redact sensitive regions in one image."""

    source = Path(input_path)
    destination = Path(output_path)
    _validate_paths(source, destination)

    image = _read_image(source)
    active_detector = detector or HaarFaceDetector()
    detections = tuple(active_detector.detect(image))
    sanitized = redact_regions(image, detections, style=style)
    _write_image(destination, sanitized)

    return ProcessResult(
        input_path=source,
        output_path=destination,
        style=style,
        detector=type(active_detector).__name__,
        detections=detections,
    )


def _validate_paths(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"input image does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("input and output paths must be different")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported input format: {source.suffix or '<none>'}")
    if destination.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported output format: {destination.suffix or '<none>'}")


def _read_image(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"file is not a readable image: {path}")
    return image


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix.lower(), image)
    if not success:
        raise ValueError(f"could not encode output image: {path}")
    encoded.tofile(path)
