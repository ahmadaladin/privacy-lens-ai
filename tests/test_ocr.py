import json
from pathlib import Path

import pytest

from privacylens.models import BoundingBox, Detection
from privacylens.ocr import OCRObservation, OCRSidecar, load_ocr_sidecar

VALID_SHA256 = "a" * 64


def test_load_ocr_sidecar_maps_only_observations_containing_pii(tmp_path: Path) -> None:
    path = tmp_path / "ocr.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "input_sha256": VALID_SHA256,
                "observations": [
                    {
                        "text": "Contact fake.person@example.com",
                        "box": [1, 2, 9, 6],
                        "score": 0.94,
                    },
                    {"text": "Invoice date", "box": [1, 7, 9, 10], "score": None},
                ],
            }
        ),
        encoding="utf-8",
    )

    sidecar = load_ocr_sidecar(path)

    assert sidecar.pii_detections() == (Detection("email", BoundingBox(1, 2, 9, 6), None),)


def test_multiple_pii_kinds_map_to_one_image_region() -> None:
    sidecar = OCRSidecar(
        input_sha256=VALID_SHA256,
        observations=(
            OCRObservation(
                text="fake@example.com +60 12-345 6789",
                box=BoundingBox(1, 2, 9, 6),
                score=0.9,
            ),
        ),
    )

    assert sidecar.pii_detections() == (Detection("email_phone", BoundingBox(1, 2, 9, 6), None),)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": "2.0"}, "schema_version"),
        ({"input_sha256": "A" * 64}, "lowercase SHA-256"),
        ({"observations": [{"text": "", "box": [1, 1, 2, 2], "score": None}]}, "non-empty"),
        (
            {"observations": [{"text": "private", "box": [1, 1, True, 2], "score": None}]},
            "integer",
        ),
        (
            {"observations": [{"text": "private", "box": [1, 1, 2, 2], "score": 1.1}]},
            "between 0 and 1",
        ),
        ({"unexpected": True}, "unknown OCR-sidecar key"),
    ],
)
def test_ocr_sidecar_rejects_unsafe_or_unknown_values_without_echoing_text(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    sensitive_value = "private.person@example.com"
    data: dict[str, object] = {
        "schema_version": "1.0",
        "input_sha256": VALID_SHA256,
        "observations": [{"text": sensitive_value, "box": [1, 1, 2, 2], "score": None}],
    }
    data.update(change)
    path = tmp_path / "ocr.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message) as error:
        load_ocr_sidecar(path)

    assert sensitive_value not in str(error.value)


def test_ocr_sidecar_rejects_duplicate_observations() -> None:
    observation = OCRObservation("fake@example.com", BoundingBox(1, 1, 2, 2))

    with pytest.raises(ValueError, match="duplicates"):
        OCRSidecar(VALID_SHA256, (observation, observation))


def test_sensitive_serializer_is_explicit_about_including_ocr_text() -> None:
    sidecar = OCRSidecar(
        VALID_SHA256,
        (OCRObservation("fake@example.com", BoundingBox(1, 1, 2, 2)),),
    )

    assert sidecar.to_sensitive_dict()["observations"][0]["text"] == "fake@example.com"  # type: ignore[index]
