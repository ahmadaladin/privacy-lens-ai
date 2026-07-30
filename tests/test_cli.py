import json
from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np

from privacylens import cli
from privacylens.models import BoundingBox, Detection
from privacylens.ocr import OCRExtraction, OCRObservation, OCRSidecar


class FixedDetector:
    def detect(self, image: np.ndarray) -> list[Detection]:
        return [Detection("face", BoundingBox(1, 1, 4, 4), 0.9)]


class FixedOCRExtractor:
    def extract(self, source: Path, *, input_sha256: str) -> OCRExtraction:
        return OCRExtraction(
            sidecar=OCRSidecar(
                input_sha256=input_sha256,
                observations=(
                    OCRObservation(
                        "fake.person@example.com",
                        BoundingBox(1, 1, 5, 5),
                        0.95,
                    ),
                ),
            ),
            engine="tesseract",
            engine_version="5.3.4",
            languages=("eng",),
        )


def test_batch_cli_reports_partial_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert cv2.imwrite(
        str(input_dir / "valid.png"),
        np.full((6, 6, 3), 255, dtype=np.uint8),
    )
    (input_dir / "bad.jpg").write_bytes(b"broken")

    original_process_directory = cli.process_directory

    def process_with_fixed_detector(input_path, output_path, *, style, ocr_extractor):
        assert ocr_extractor is None
        return original_process_directory(
            input_path,
            output_path,
            style=style,
            detector=FixedDetector(),
        )

    monkeypatch.setattr(cli, "process_directory", process_with_fixed_detector)

    exit_code = cli.main([str(input_dir), str(output_dir), "--batch"])

    assert exit_code == 1
    assert "Processed 1 image(s); 1 failed" in capsys.readouterr().out


def test_policy_option_is_rejected_outside_text_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--policy",
            str(tmp_path / "policy.json"),
        ]
    )

    assert exit_code == 2
    assert "--policy requires --text" in capsys.readouterr().err


def test_review_plan_is_rejected_in_batch_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input"),
            str(tmp_path / "output"),
            "--batch",
            "--review-plan",
            str(tmp_path / "review.json"),
        ]
    )

    assert exit_code == 2
    assert "valid only for single-image mode" in capsys.readouterr().err


def test_review_plan_requires_manifest_in_image_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--review-plan",
            str(tmp_path / "review.json"),
        ]
    )

    assert exit_code == 2
    assert "requires --manifest" in capsys.readouterr().err


def test_ocr_sidecar_requires_manifest_in_image_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--ocr-sidecar",
            str(tmp_path / "ocr.json"),
        ]
    )

    assert exit_code == 2
    assert "--ocr-sidecar requires --manifest" in capsys.readouterr().err


def test_ocr_sidecar_is_rejected_in_text_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.txt"),
            str(tmp_path / "output.txt"),
            "--text",
            "--ocr-sidecar",
            str(tmp_path / "ocr.json"),
        ]
    )

    assert exit_code == 2
    assert "valid only for single-image mode" in capsys.readouterr().err


def test_ocr_sidecar_cli_redacts_and_writes_value_free_audit(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    sidecar = tmp_path / "ocr.json"
    manifest = tmp_path / "audit.json"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    sensitive_value = "fake.person@example.com"
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "input_sha256": sha256(source.read_bytes()).hexdigest(),
                "observations": [
                    {
                        "text": sensitive_value,
                        "box": [1, 1, 5, 5],
                        "score": 0.95,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            str(source),
            str(destination),
            "--ocr-sidecar",
            str(sidecar),
            "--style",
            "solid",
            "--manifest",
            str(manifest),
        ]
    )

    assert exit_code == 0
    assert np.all(cv2.imread(str(destination))[1:5, 1:5] == 0)
    assert sensitive_value not in manifest.read_text(encoding="utf-8")
    assert "Redacted 1 OCR observation region(s) containing PII" in capsys.readouterr().out


def test_ocr_engine_requires_manifest_in_image_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--ocr-engine",
            "tesseract",
        ]
    )

    assert exit_code == 2
    assert "--ocr-engine requires --manifest" in capsys.readouterr().err


def test_ocr_language_requires_engine(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--ocr-language",
            "eng+ara",
        ]
    )

    assert exit_code == 2
    assert "--ocr-language requires --ocr-engine" in capsys.readouterr().err


def test_ocr_engine_cli_runs_local_extractor_and_writes_audit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    manifest = tmp_path / "audit.json"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    monkeypatch.setattr(cli, "TesseractOCR", lambda *, language: FixedOCRExtractor())

    exit_code = cli.main(
        [
            str(source),
            str(destination),
            "--ocr-engine",
            "tesseract",
            "--ocr-language",
            "eng",
            "--style",
            "solid",
            "--manifest",
            str(manifest),
        ]
    )

    assert exit_code == 0
    assert np.all(cv2.imread(str(destination))[1:5, 1:5] == 0)
    audit = json.loads(manifest.read_text(encoding="utf-8"))
    assert audit["ocr_engine"] == "tesseract"
    assert audit["ocr_engine_version"] == "5.3.4"
    assert audit["ocr_languages"] == ["eng"]
    assert "Redacted 1 OCR observation region(s) containing PII" in capsys.readouterr().out


def test_ocr_engine_cli_processes_batch_without_requiring_custom_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert cv2.imwrite(
        str(input_dir / "one.png"),
        np.full((8, 8, 3), 255, dtype=np.uint8),
    )
    monkeypatch.setattr(cli, "TesseractOCR", lambda *, language: FixedOCRExtractor())

    exit_code = cli.main(
        [
            str(input_dir),
            str(output_dir),
            "--batch",
            "--ocr-engine",
            "tesseract",
            "--ocr-language",
            "eng",
            "--style",
            "solid",
        ]
    )

    assert exit_code == 0
    output = cv2.imread(str(output_dir / "sanitized" / "one.png"))
    assert np.all(output[1:5, 1:5] == 0)
    batch = json.loads((output_dir / "batch-manifest.json").read_text(encoding="utf-8"))
    assert batch["processing_mode"] == "ocr"
    assert batch["processor"] == "FixedOCRExtractor"
    assert "Processed 1 image(s); 0 failed" in capsys.readouterr().out
