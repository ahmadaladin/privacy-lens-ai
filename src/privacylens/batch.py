"""Fault-isolated batch processing for image datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from privacylens.detectors.base import Detector
from privacylens.detectors.haar_face import HaarFaceDetector
from privacylens.ocr import OCRExtractor
from privacylens.pipeline import SUPPORTED_SUFFIXES, process_image

BATCH_MANIFEST_SCHEMA_VERSION = "1.1"


@dataclass(frozen=True, slots=True)
class BatchItemResult:
    """Outcome for one source image, without exposing absolute source paths."""

    input_name: str
    status: Literal["processed", "failed"]
    output_path: str | None = None
    manifest_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "input_name": self.input_name,
            "status": self.status,
            "output_path": self.output_path,
            "manifest_path": self.manifest_path,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class BatchResult:
    """Summary of a completed batch."""

    items: tuple[BatchItemResult, ...]
    processing_mode: Literal["detector", "ocr"]
    processor: str

    @property
    def processed_count(self) -> int:
        return sum(item.status == "processed" for item in self.items)

    @property
    def failed_count(self) -> int:
        return sum(item.status == "failed" for item in self.items)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": BATCH_MANIFEST_SCHEMA_VERSION,
            "processing_mode": self.processing_mode,
            "processor": self.processor,
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "items": [item.to_dict() for item in self.items],
        }

    def write_manifest(self, path: str | Path) -> None:
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def process_directory(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    style: str = "blur",
    detector: Detector | None = None,
    ocr_extractor: OCRExtractor | None = None,
) -> BatchResult:
    """Process supported images directly inside a directory.

    A failed image receives a metadata-only quarantine record. The sensitive
    source is never copied, moved, or modified.
    """

    source_dir = Path(input_dir)
    destination_dir = Path(output_dir)
    _validate_directories(source_dir, destination_dir)
    if detector is not None and ocr_extractor is not None:
        raise ValueError("detector and ocr_extractor cannot be used together")

    sanitized_dir = destination_dir / "sanitized"
    manifests_dir = destination_dir / "manifests"
    quarantine_dir = destination_dir / "quarantine"
    active_detector = detector or (HaarFaceDetector() if ocr_extractor is None else None)
    processing_mode: Literal["detector", "ocr"] = "ocr" if ocr_extractor is not None else "detector"
    active_processor = ocr_extractor if ocr_extractor is not None else active_detector
    assert active_processor is not None
    processor = type(active_processor).__name__
    items: list[BatchItemResult] = []

    candidates = sorted(
        (
            path
            for path in source_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.name.casefold(),
    )

    for source in candidates:
        output_path = sanitized_dir / source.name
        manifest_path = manifests_dir / f"{source.name}.json"
        try:
            result = process_image(
                source,
                output_path,
                style=style,
                detector=active_detector,
                ocr_extractor=ocr_extractor,
            )
            result.write_manifest(manifest_path)
        except Exception as error:
            quarantine_path = quarantine_dir / f"{source.name}.error.json"
            item = BatchItemResult(
                input_name=source.name,
                status="failed",
                error_type=type(error).__name__,
                error_message=_safe_error_message(error, source),
            )
            _write_quarantine_record(quarantine_path, item)
            items.append(item)
            continue

        items.append(
            BatchItemResult(
                input_name=source.name,
                status="processed",
                output_path=str(output_path.relative_to(destination_dir)),
                manifest_path=str(manifest_path.relative_to(destination_dir)),
            )
        )

    batch_result = BatchResult(
        items=tuple(items),
        processing_mode=processing_mode,
        processor=processor,
    )
    batch_result.write_manifest(destination_dir / "batch-manifest.json")
    return batch_result


def _validate_directories(source_dir: Path, destination_dir: Path) -> None:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"input directory does not exist: {source_dir}")

    source_resolved = source_dir.resolve()
    destination_resolved = destination_dir.resolve()
    if source_resolved == destination_resolved:
        raise ValueError("input and output directories must be different")
    if source_resolved in destination_resolved.parents:
        raise ValueError("output directory must not be inside the input directory")


def _safe_error_message(error: Exception, source: Path) -> str:
    return str(error).replace(str(source), source.name)


def _write_quarantine_record(path: Path, item: BatchItemResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(item.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
