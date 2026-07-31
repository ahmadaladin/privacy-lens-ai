import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from privacylens.batch import process_directory
from privacylens.models import BoundingBox, Detection
from privacylens.ocr import OCRExtraction, OCRObservation, OCRSidecar


class FixedDetector:
    def detect(self, image: np.ndarray) -> list[Detection]:
        return [Detection("face", BoundingBox(1, 1, 4, 4), 0.9)]


class FixedOCRExtractor:
    def extract(self, source: Path, *, input_sha256: str) -> OCRExtraction:
        if source.name.startswith("fail"):
            raise ValueError("synthetic OCR failure")
        observation_text = (
            "Invoice total" if source.name.startswith("clean") else "fake.person@example.com"
        )
        return OCRExtraction(
            sidecar=OCRSidecar(
                input_sha256=input_sha256,
                observations=(
                    OCRObservation(
                        observation_text,
                        BoundingBox(1, 1, 5, 5),
                        0.95,
                    ),
                ),
            ),
            engine="tesseract",
            engine_version="5.3.4",
            languages=("eng",),
        )


def test_batch_continues_after_bad_image_and_quarantines_metadata(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    valid_source = input_dir / "a-valid.png"
    invalid_source = input_dir / "b-corrupt.jpg"
    assert cv2.imwrite(str(valid_source), np.full((6, 6, 3), 255, dtype=np.uint8))
    invalid_bytes = b"not an image"
    invalid_source.write_bytes(invalid_bytes)

    result = process_directory(input_dir, output_dir, style="solid", detector=FixedDetector())

    assert result.processed_count == 1
    assert result.failed_count == 1
    assert (output_dir / "sanitized" / valid_source.name).is_file()
    assert (output_dir / "manifests" / f"{valid_source.name}.json").is_file()
    quarantine_path = output_dir / "quarantine" / f"{invalid_source.name}.error.json"
    assert quarantine_path.is_file()
    assert invalid_source.read_bytes() == invalid_bytes
    assert not (output_dir / "quarantine" / invalid_source.name).exists()

    quarantine = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert quarantine["input_name"] == invalid_source.name
    assert quarantine["status"] == "failed"
    assert quarantine["error_type"] == "ValueError"
    assert str(input_dir) not in quarantine["error_message"]


def test_batch_manifest_is_deterministic_and_uses_relative_output_paths(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for name in ("z-last.png", "A-first.jpg"):
        assert cv2.imwrite(
            str(input_dir / name),
            np.full((6, 6, 3), 255, dtype=np.uint8),
        )
    (input_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    result = process_directory(input_dir, output_dir, detector=FixedDetector())

    assert [item.input_name for item in result.items] == ["A-first.jpg", "z-last.png"]
    manifest = json.loads((output_dir / "batch-manifest.json").read_text(encoding="utf-8"))
    assert manifest["processed_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["processing_mode"] == "detector"
    assert manifest["processor"] == "FixedDetector"
    assert manifest["risk_summary_path"] == "dataset-risk-summary.json"
    assert manifest["items"][0]["output_path"] == "sanitized/A-first.jpg"
    assert str(tmp_path) not in json.dumps(manifest)


def test_batch_rejects_output_directory_inside_sensitive_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="must not be inside"):
        process_directory(input_dir, input_dir / "output", detector=FixedDetector())


def test_ocr_batch_is_fault_isolated_and_preserves_per_image_metadata(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    for name in ("process.png", "clean.png", "fail.png"):
        assert cv2.imwrite(
            str(input_dir / name),
            np.full((8, 8, 3), 255, dtype=np.uint8),
        )

    result = process_directory(
        input_dir,
        output_dir,
        style="solid",
        ocr_extractor=FixedOCRExtractor(),
    )

    assert result.processed_count == 2
    assert result.failed_count == 1
    output = cv2.imread(str(output_dir / "sanitized" / "process.png"))
    assert np.all(output[1:5, 1:5] == 0)
    audit_text = (output_dir / "manifests" / "process.png.json").read_text(encoding="utf-8")
    assert "fake.person@example.com" not in audit_text
    audit = json.loads(audit_text)
    assert audit["ocr_engine"] == "tesseract"
    assert audit["ocr_engine_version"] == "5.3.4"
    assert audit["ocr_languages"] == ["eng"]

    batch = json.loads((output_dir / "batch-manifest.json").read_text(encoding="utf-8"))
    assert batch["schema_version"] == "1.2"
    assert batch["processing_mode"] == "ocr"
    assert batch["processor"] == "FixedOCRExtractor"
    assert batch["processed_count"] == 2
    assert batch["failed_count"] == 1
    quarantine = (output_dir / "quarantine" / "fail.png.error.json").read_text(encoding="utf-8")
    assert "fake.person@example.com" not in quarantine
    summary_text = (output_dir / "dataset-risk-summary.json").read_text(encoding="utf-8")
    assert "fake.person@example.com" not in summary_text
    assert str(tmp_path) not in summary_text
    summary = json.loads(summary_text)
    assert summary == {
        "schema_version": "1.0",
        "interpretation": "operational_counts_only_not_accuracy_or_safety_metrics",
        "processing_mode": "ocr",
        "processor": "FixedOCRExtractor",
        "completion_status": "partial",
        "processing_attention_required": True,
        "candidate_count": 3,
        "processed_count": 2,
        "failed_count": 1,
        "images_with_findings": 1,
        "images_without_findings": 1,
        "total_findings": 1,
        "findings_by_kind": {"email": 1},
        "ocr_observation_count": 2,
    }
    assert result.risk_summary.to_dict() == summary


def test_batch_rejects_detector_and_ocr_extractor_together(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="cannot be used together"):
        process_directory(
            input_dir,
            tmp_path / "output",
            detector=FixedDetector(),
            ocr_extractor=FixedOCRExtractor(),
        )


def test_empty_batch_writes_attention_required_risk_summary(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    result = process_directory(input_dir, output_dir, detector=FixedDetector())

    assert result.risk_summary.completion_status == "empty"
    summary = json.loads((output_dir / "dataset-risk-summary.json").read_text(encoding="utf-8"))
    assert summary["candidate_count"] == 0
    assert summary["completion_status"] == "empty"
    assert summary["processing_attention_required"] is True
    assert summary["ocr_observation_count"] is None
