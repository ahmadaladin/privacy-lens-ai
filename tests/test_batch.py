import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from privacylens.batch import process_directory
from privacylens.models import BoundingBox, Detection


class FixedDetector:
    def detect(self, image: np.ndarray) -> list[Detection]:
        return [Detection("face", BoundingBox(1, 1, 4, 4), 0.9)]


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
    assert manifest["items"][0]["output_path"] == "sanitized/A-first.jpg"
    assert str(tmp_path) not in json.dumps(manifest)


def test_batch_rejects_output_directory_inside_sensitive_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="must not be inside"):
        process_directory(input_dir, input_dir / "output", detector=FixedDetector())
