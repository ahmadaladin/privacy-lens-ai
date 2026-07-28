import json
from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from privacylens.models import BoundingBox, Detection
from privacylens.ocr import OCRObservation, OCRSidecar
from privacylens.pipeline import process_image
from privacylens.review import ReviewPlan


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
    assert audit["schema_version"] == "1.2"
    assert audit["detector"] == "FixedDetector"
    assert audit["input_sha256"] == sha256(source.read_bytes()).hexdigest()
    assert audit["human_reviewed"] is False
    assert audit["review_plan_schema_version"] is None
    assert audit["ocr_sidecar_schema_version"] is None
    assert audit["ocr_sidecar_observation_count"] is None
    assert audit["detections"][0]["kind"] == "face"


def test_manual_review_plan_replaces_detector_regions_and_is_auditable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    manifest = tmp_path / "audit.json"
    image = np.full((8, 8, 3), 255, dtype=np.uint8)
    assert cv2.imwrite(str(source), image)
    input_sha256 = sha256(source.read_bytes()).hexdigest()
    review_plan = ReviewPlan(
        input_sha256=input_sha256,
        detections=(Detection("face", BoundingBox(2, 2, 6, 6), None),),
    )

    result = process_image(
        source,
        destination,
        style="solid",
        review_plan=review_plan,
    )
    result.write_manifest(manifest)

    output = cv2.imread(str(destination))
    assert np.all(output[2:6, 2:6] == 0)
    assert np.all(output[:2] == 255)
    audit = json.loads(manifest.read_text(encoding="utf-8"))
    assert audit["detector"] == "ManualReviewPlan"
    assert audit["human_reviewed"] is True
    assert audit["review_plan_schema_version"] == "1.0"
    assert audit["input_sha256"] == input_sha256


def test_review_plan_rejects_wrong_source_without_writing_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    review_plan = ReviewPlan(input_sha256="0" * 64, detections=())

    with pytest.raises(ValueError, match="fingerprint does not match"):
        process_image(source, destination, review_plan=review_plan)

    assert not destination.exists()


def test_review_plan_rejects_out_of_bounds_region_without_writing_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    review_plan = ReviewPlan(
        input_sha256=sha256(source.read_bytes()).hexdigest(),
        detections=(Detection("face", BoundingBox(1, 1, 9, 7), None),),
    )

    with pytest.raises(ValueError, match="outside the source image"):
        process_image(source, destination, review_plan=review_plan)

    assert not destination.exists()


def test_review_plan_and_detector_are_mutually_exclusive(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    review_plan = ReviewPlan(
        input_sha256=sha256(source.read_bytes()).hexdigest(),
        detections=(),
    )

    with pytest.raises(ValueError, match="cannot be used together"):
        process_image(
            source,
            destination,
            detector=FixedDetector(),
            review_plan=review_plan,
        )


def test_ocr_sidecar_redacts_pii_regions_without_leaking_text_to_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    manifest = tmp_path / "audit.json"
    image = np.full((10, 10, 3), 255, dtype=np.uint8)
    assert cv2.imwrite(str(source), image)
    sensitive_value = "fake.person@example.com"
    sidecar = OCRSidecar(
        input_sha256=sha256(source.read_bytes()).hexdigest(),
        observations=(
            OCRObservation(sensitive_value, BoundingBox(1, 1, 5, 5), 0.96),
            OCRObservation("Invoice date", BoundingBox(6, 6, 9, 9), 0.99),
        ),
    )

    result = process_image(source, destination, style="solid", ocr_sidecar=sidecar)
    result.write_manifest(manifest)

    output = cv2.imread(str(destination))
    assert np.all(output[1:5, 1:5] == 0)
    assert np.all(output[6:9, 6:9] == 255)
    audit_text = manifest.read_text(encoding="utf-8")
    assert sensitive_value not in audit_text
    audit = json.loads(audit_text)
    assert audit["detector"] == "OCRSidecarPIIMapper"
    assert audit["ocr_sidecar_schema_version"] == "1.0"
    assert audit["ocr_sidecar_observation_count"] == 2
    assert audit["detections"] == [{"kind": "email", "score": None, "box": [1, 1, 5, 5]}]


def test_ocr_sidecar_rejects_wrong_source_without_writing_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    sidecar = OCRSidecar(input_sha256="0" * 64, observations=())

    with pytest.raises(ValueError, match="fingerprint does not match"):
        process_image(source, destination, ocr_sidecar=sidecar)

    assert not destination.exists()


def test_ocr_sidecar_rejects_out_of_bounds_observation_before_writing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.png"
    destination = tmp_path / "output.png"
    assert cv2.imwrite(str(source), np.full((8, 8, 3), 255, dtype=np.uint8))
    sidecar = OCRSidecar(
        input_sha256=sha256(source.read_bytes()).hexdigest(),
        observations=(OCRObservation("fake@example.com", BoundingBox(1, 1, 9, 7)),),
    )

    with pytest.raises(ValueError, match="outside the source image"):
        process_image(source, destination, ocr_sidecar=sidecar)

    assert not destination.exists()


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
