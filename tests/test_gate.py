import json
from pathlib import Path

import pytest

from privacylens.gate import BatchEvidenceError, main, verify_batch_output


def write_batch_evidence(
    root: Path,
    *,
    processed: tuple[str, ...] = ("safe.png",),
    failed: tuple[str, ...] = (),
) -> None:
    items = []
    for name in processed:
        output = root / "sanitized" / name
        manifest = root / "manifests" / f"{name}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"not-opened-by-gate")
        manifest.write_text("{}\n", encoding="utf-8")
        items.append(
            {
                "input_name": name,
                "status": "processed",
                "output_path": f"sanitized/{name}",
                "manifest_path": f"manifests/{name}.json",
                "error_type": None,
                "error_message": None,
            }
        )
    for name in failed:
        item = {
            "input_name": name,
            "status": "failed",
            "output_path": None,
            "manifest_path": None,
            "error_type": "ValueError",
            "error_message": "synthetic failure\n",
        }
        quarantine = root / "quarantine" / f"{name}.error.json"
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        quarantine.write_text(json.dumps(item), encoding="utf-8")
        items.append(item)

    processed_count = len(processed)
    failed_count = len(failed)
    candidate_count = processed_count + failed_count
    if candidate_count == 0:
        status = "empty"
    elif failed_count == 0:
        status = "complete"
    elif processed_count == 0:
        status = "failed"
    else:
        status = "partial"
    root.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "1.0",
        "interpretation": "operational_counts_only_not_accuracy_or_safety_metrics",
        "processing_mode": "ocr",
        "processor": "TesseractOCR",
        "completion_status": status,
        "processing_attention_required": status != "complete",
        "candidate_count": candidate_count,
        "processed_count": processed_count,
        "failed_count": failed_count,
        "images_with_findings": processed_count,
        "images_without_findings": 0,
        "total_findings": processed_count,
        "findings_by_kind": {"email": processed_count} if processed_count else {},
        "ocr_observation_count": processed_count,
    }
    batch = {
        "schema_version": "1.2",
        "processing_mode": "ocr",
        "processor": "TesseractOCR",
        "risk_summary_path": "dataset-risk-summary.json",
        "processed_count": processed_count,
        "failed_count": failed_count,
        "items": items,
    }
    (root / "dataset-risk-summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (root / "batch-manifest.json").write_text(json.dumps(batch), encoding="utf-8")


def test_complete_non_empty_batch_passes(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)

    report = verify_batch_output(tmp_path)

    assert report.passed is True
    assert main([str(tmp_path)]) == 0


@pytest.mark.parametrize(
    ("processed", "failed", "status"),
    [
        ((), (), "empty"),
        (("safe.png",), ("broken.png",), "partial"),
        ((), ("broken.png",), "failed"),
    ],
)
def test_incomplete_but_valid_batch_returns_review_exit_code(
    tmp_path: Path,
    processed: tuple[str, ...],
    failed: tuple[str, ...],
    status: str,
) -> None:
    write_batch_evidence(tmp_path, processed=processed, failed=failed)

    report = verify_batch_output(tmp_path)

    assert report.completion_status == status
    assert report.passed is False
    assert main([str(tmp_path)]) == 1


def test_tampered_summary_is_invalid_not_merely_incomplete(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    path = tmp_path / "dataset-risk-summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["completion_status"] = "partial"
    path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(BatchEvidenceError, match="risk summary is invalid"):
        verify_batch_output(tmp_path)
    assert main([str(tmp_path)]) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_name", "../safe.png"),
        ("output_path", "../safe.png"),
        ("manifest_path", "/tmp/audit.json"),
    ],
)
def test_unsafe_artifact_references_are_rejected(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    write_batch_evidence(tmp_path)
    path = tmp_path / "batch-manifest.json"
    batch = json.loads(path.read_text(encoding="utf-8"))
    batch["items"][0][field] = value
    path.write_text(json.dumps(batch), encoding="utf-8")

    with pytest.raises(BatchEvidenceError, match="unsafe"):
        verify_batch_output(tmp_path)


def test_missing_artifact_is_rejected(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    (tmp_path / "sanitized" / "safe.png").unlink()

    with pytest.raises(BatchEvidenceError, match="artifact is missing"):
        verify_batch_output(tmp_path)


def test_boolean_batch_count_is_rejected(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    path = tmp_path / "batch-manifest.json"
    batch = json.loads(path.read_text(encoding="utf-8"))
    batch["processed_count"] = True
    path.write_text(json.dumps(batch), encoding="utf-8")

    with pytest.raises(BatchEvidenceError, match="non-negative integer"):
        verify_batch_output(tmp_path)


def test_symlinked_artifact_cannot_escape_output_directory(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    artifact = tmp_path / "sanitized" / "safe.png"
    artifact.unlink()
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"outside")
    artifact.symlink_to(outside)

    with pytest.raises(BatchEvidenceError, match="escapes"):
        verify_batch_output(tmp_path)


def test_stale_unlisted_artifact_is_rejected(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    (tmp_path / "sanitized" / "stale.png").write_bytes(b"stale")

    with pytest.raises(BatchEvidenceError, match="inventory disagrees"):
        verify_batch_output(tmp_path)


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    write_batch_evidence(tmp_path)
    path = tmp_path / "batch-manifest.json"
    text = path.read_text(encoding="utf-8").replace(
        '"schema_version": "1.2"',
        '"schema_version": "1.2", "schema_version": "1.2"',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(BatchEvidenceError, match="duplicate keys"):
        verify_batch_output(tmp_path)


def test_gate_output_is_value_free(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_batch_evidence(tmp_path, processed=("secret-person.png",))

    assert main([str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "secret-person.png" not in output
    assert str(tmp_path) not in output
    assert "candidates=1" in output
