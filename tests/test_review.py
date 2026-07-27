import json
from pathlib import Path

import pytest

from privacylens.models import BoundingBox, Detection
from privacylens.review import ReviewPlan, load_review_plan

VALID_SHA256 = "a" * 64


def test_load_review_plan_parses_value_free_regions(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "input_sha256": VALID_SHA256,
                "regions": [{"kind": "face", "box": [1, 2, 5, 6]}],
            }
        ),
        encoding="utf-8",
    )

    plan = load_review_plan(path)

    assert plan == ReviewPlan(
        input_sha256=VALID_SHA256,
        detections=(Detection("face", BoundingBox(1, 2, 5, 6), None),),
    )
    assert plan.to_dict()["regions"] == [{"kind": "face", "box": [1, 2, 5, 6]}]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": "2.0"}, "schema_version"),
        ({"input_sha256": "A" * 64}, "lowercase SHA-256"),
        ({"regions": [{"kind": "Face", "box": [1, 1, 2, 2]}]}, "kind"),
        ({"regions": [{"kind": "face", "box": [1, 1, True, 2]}]}, "integer"),
        ({"regions": [{"kind": "face", "box": [2, 1, 2, 3]}]}, "non-empty"),
        ({"unexpected": True}, "unknown review-plan key"),
    ],
)
def test_review_plan_rejects_unsafe_or_unknown_values(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    data: dict[str, object] = {
        "schema_version": "1.0",
        "input_sha256": VALID_SHA256,
        "regions": [],
    }
    data.update(change)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_review_plan(path)


def test_review_plan_rejects_duplicate_regions() -> None:
    detection = Detection("face", BoundingBox(1, 1, 2, 2), None)

    with pytest.raises(ValueError, match="duplicates"):
        ReviewPlan(
            input_sha256=VALID_SHA256,
            detections=(detection, detection),
        )


@pytest.mark.parametrize(
    "detection",
    [
        Detection("Face", BoundingBox(1, 1, 2, 2), None),
        Detection("face", BoundingBox(-1, 1, 2, 2), None),
        Detection("face", BoundingBox(1, 1, 2, 2), 0.9),
    ],
)
def test_direct_review_plan_api_enforces_loader_invariants(
    detection: Detection,
) -> None:
    with pytest.raises(ValueError):
        ReviewPlan(input_sha256=VALID_SHA256, detections=(detection,))


def test_review_plan_requires_immutable_detection_collection() -> None:
    with pytest.raises(ValueError, match="immutable tuple"):
        ReviewPlan(input_sha256=VALID_SHA256, detections=[])  # type: ignore[arg-type]


def test_review_plan_allows_explicit_zero_region_approval() -> None:
    plan = ReviewPlan(input_sha256=VALID_SHA256, detections=())

    assert plan.detections == ()
