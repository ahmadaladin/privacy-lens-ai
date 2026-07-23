import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from privacylens.models import BoundingBox, Detection
from privacylens.pipeline import process_image


class FixedDetector:
    def detect(self, image: np.ndarray) -> list[Detection]:
        return [Detection("face", BoundingBox(1, 1, 4, 4), 0.9)]


def test_process_image_writes_output_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    manifest = tmp_path / "audit.json"
    image = np.full((6, 6, 3), 255, dtype=np.uint8)
    assert cv2.imwrite(str(source), image)

    result = process_image(source, destination, style="solid", detector=FixedDetector())
    result.write_manifest(manifest)

    output = cv2.imread(str(destination))
    assert destination.is_file()
    assert manifest.is_file()
    assert np.all(output[1:4, 1:4] == 0)
    audit = json.loads(manifest.read_text(encoding="utf-8"))
    assert audit["schema_version"] == "1.0"
    assert audit["detector"] == "FixedDetector"
    assert audit["detections"][0]["kind"] == "face"


def test_process_image_refuses_to_overwrite_sensitive_source(tmp_path: Path) -> None:
    source = tmp_path / "original.png"
    original = np.full((6, 6, 3), 255, dtype=np.uint8)
    assert cv2.imwrite(str(source), original)

    with pytest.raises(ValueError, match="input and output paths must be different"):
        process_image(source, source, detector=FixedDetector())

    assert np.array_equal(cv2.imread(str(source)), original)


def test_processing_strips_embedded_image_metadata(tmp_path: Path) -> None:
    source = tmp_path / "with-metadata.jpg"
    destination = tmp_path / "sanitized.jpg"
    image = Image.new("RGB", (12, 12), color="white")
    exif = Image.Exif()
    exif[0x010E] = "private test description"
    image.save(source, exif=exif)

    process_image(source, destination, detector=FixedDetector())

    with Image.open(destination) as sanitized:
        assert len(sanitized.getexif()) == 0
