"""End-to-end image processing and audit reporting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from privacylens.detectors.base import Detector
from privacylens.detectors.haar_face import HaarFaceDetector
from privacylens.models import Detection
from privacylens.ocr import OCR_SIDECAR_SCHEMA_VERSION, OCRExtractor, OCRSidecar
from privacylens.redaction import redact_regions
from privacylens.review import REVIEW_PLAN_SCHEMA_VERSION, ReviewPlan

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png"}
MANIFEST_SCHEMA_VERSION = "1.3"


@dataclass(frozen=True, slots=True)
class ProcessResult:
    input_path: Path
    output_path: Path
    style: str
    detector: str
    detections: tuple[Detection, ...]
    input_sha256: str
    human_reviewed: bool
    ocr_sidecar_observation_count: int | None
    ocr_engine: str | None
    ocr_engine_version: str | None
    ocr_languages: tuple[str, ...] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "input_path": str(self.input_path),
            "output_path": str(self.output_path),
            "input_sha256": self.input_sha256,
            "style": self.style,
            "detector": self.detector,
            "human_reviewed": self.human_reviewed,
            "review_plan_schema_version": (
                REVIEW_PLAN_SCHEMA_VERSION if self.human_reviewed else None
            ),
            "ocr_sidecar_schema_version": (
                OCR_SIDECAR_SCHEMA_VERSION
                if self.ocr_sidecar_observation_count is not None
                else None
            ),
            "ocr_sidecar_observation_count": self.ocr_sidecar_observation_count,
            "ocr_engine": self.ocr_engine,
            "ocr_engine_version": self.ocr_engine_version,
            "ocr_languages": list(self.ocr_languages) if self.ocr_languages else None,
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
    review_plan: ReviewPlan | None = None,
    ocr_sidecar: OCRSidecar | None = None,
    ocr_extractor: OCRExtractor | None = None,
) -> ProcessResult:
    """Detect and redact sensitive regions in one image."""

    source = Path(input_path)
    destination = Path(output_path)
    _validate_paths(source, destination)
    modes = sum(value is not None for value in (detector, review_plan, ocr_sidecar, ocr_extractor))
    if modes > 1:
        raise ValueError(
            "detector, review_plan, ocr_sidecar, and ocr_extractor cannot be used together"
        )

    image, input_sha256 = _read_image(source)
    active_ocr_sidecar = ocr_sidecar
    ocr_engine = "external_sidecar" if ocr_sidecar is not None else None
    ocr_engine_version = None
    ocr_languages = None
    if ocr_extractor is not None:
        extraction = ocr_extractor.extract(source, input_sha256=input_sha256)
        active_ocr_sidecar = extraction.sidecar
        ocr_engine = extraction.engine
        ocr_engine_version = extraction.engine_version
        ocr_languages = extraction.languages
    if review_plan is not None and review_plan.input_sha256 != input_sha256:
        raise ValueError("review plan fingerprint does not match the source image")
    if active_ocr_sidecar is not None and active_ocr_sidecar.input_sha256 != input_sha256:
        raise ValueError("OCR sidecar fingerprint does not match the source image")
    if review_plan is not None:
        height, width = image.shape[:2]
        review_plan.validate_for_image(width=width, height=height)
        detections = review_plan.detections
        detector_name = "ManualReviewPlan"
    elif active_ocr_sidecar is not None:
        height, width = image.shape[:2]
        active_ocr_sidecar.validate_for_image(width=width, height=height)
        detections = active_ocr_sidecar.pii_detections()
        detector_name = (
            "OCRSidecarPIIMapper"
            if ocr_extractor is None
            else f"{extraction.engine.title()}OCRPIIMapper"
        )
    else:
        active_detector = detector or HaarFaceDetector()
        detections = tuple(active_detector.detect(image))
        detector_name = type(active_detector).__name__
    sanitized = redact_regions(image, detections, style=style)
    _write_image(destination, sanitized)

    return ProcessResult(
        input_path=source,
        output_path=destination,
        style=style,
        detector=detector_name,
        detections=detections,
        input_sha256=input_sha256,
        human_reviewed=review_plan is not None,
        ocr_sidecar_observation_count=(
            len(active_ocr_sidecar.observations) if active_ocr_sidecar is not None else None
        ),
        ocr_engine=ocr_engine,
        ocr_engine_version=ocr_engine_version,
        ocr_languages=ocr_languages,
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


def _read_image(path: Path) -> tuple[np.ndarray, str]:
    encoded = np.fromfile(path, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"file is not a readable image: {path}")
    return image, hashlib.sha256(encoded).hexdigest()


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    success, encoded = cv2.imencode(path.suffix.lower(), image)
    if not success:
        raise ValueError(f"could not encode output image: {path}")
    encoded.tofile(path)
