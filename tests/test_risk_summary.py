import json
from pathlib import Path

import pytest

from privacylens.risk_summary import DatasetRiskSummary, load_risk_summary


def make_summary(**changes) -> DatasetRiskSummary:
    values = {
        "processing_mode": "ocr",
        "processor": "TesseractOCR",
        "candidate_count": 3,
        "processed_count": 2,
        "failed_count": 1,
        "images_with_findings": 1,
        "images_without_findings": 1,
        "total_findings": 2,
        "findings_by_kind": (("email", 1), ("phone", 1)),
        "ocr_observation_count": 8,
    }
    values.update(changes)
    return DatasetRiskSummary(**values)


@pytest.mark.parametrize(
    ("changes", "status", "processing_attention_required"),
    [
        (
            {
                "candidate_count": 0,
                "processed_count": 0,
                "failed_count": 0,
                "images_with_findings": 0,
                "images_without_findings": 0,
                "total_findings": 0,
                "findings_by_kind": (),
                "ocr_observation_count": 0,
            },
            "empty",
            True,
        ),
        ({"failed_count": 0, "candidate_count": 2}, "complete", False),
        ({}, "partial", True),
        (
            {
                "processed_count": 0,
                "failed_count": 3,
                "images_with_findings": 0,
                "images_without_findings": 0,
                "total_findings": 0,
                "findings_by_kind": (),
                "ocr_observation_count": 0,
            },
            "failed",
            True,
        ),
    ],
)
def test_completion_status_is_derived_from_exact_counts(
    changes: dict[str, object],
    status: str,
    processing_attention_required: bool,
) -> None:
    summary = make_summary(**changes)

    assert summary.completion_status == status
    assert summary.processing_attention_required is processing_attention_required


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"processed_count": 3}, "candidate_count"),
        ({"images_with_findings": 2}, "finding-image"),
        ({"findings_by_kind": (("phone", 1), ("email", 1))}, "uniquely sorted"),
        ({"total_findings": 3}, "total_findings"),
        (
            {
                "processing_mode": "detector",
                "ocr_observation_count": 8,
            },
            "must not claim OCR",
        ),
    ],
)
def test_summary_rejects_inconsistent_or_misleading_counts(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        make_summary(**changes)


def test_summary_declares_counts_are_not_accuracy_or_safety_metrics() -> None:
    data = make_summary().to_dict()

    assert data["interpretation"] == "operational_counts_only_not_accuracy_or_safety_metrics"
    assert data["findings_by_kind"] == {"email": 1, "phone": 1}
    assert not {"input_path", "output_path", "input_name"} & set(data)


def test_written_summary_round_trips_through_strict_loader(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    expected = make_summary()
    expected.write(path)

    assert load_risk_summary(path) == expected


def test_loader_rejects_unknown_fields_and_inconsistent_derived_values(tmp_path: Path) -> None:
    path = tmp_path / "summary.json"
    data = make_summary().to_dict()
    data["completion_status"] = "complete"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="inconsistent derived fields"):
        load_risk_summary(path)

    data = make_summary().to_dict()
    data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly the supported fields"):
        load_risk_summary(path)
