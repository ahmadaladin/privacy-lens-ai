from privacylens.models import BoundingBox, Detection


def test_bounding_box_clips_to_image_boundaries() -> None:
    box = BoundingBox(-3, 2, 15, 20).clipped(width=10, height=12)

    assert box == BoundingBox(0, 2, 10, 12)


def test_detection_serializes_for_audit_manifest() -> None:
    detection = Detection("face", BoundingBox(1, 2, 3, 4), 0.87654)

    assert detection.to_dict() == {
        "kind": "face",
        "score": 0.8765,
        "box": [1, 2, 3, 4],
    }


def test_detection_without_calibrated_score_is_honest_in_manifest() -> None:
    detection = Detection("face", BoundingBox(1, 2, 3, 4), None)

    assert detection.to_dict()["score"] is None
