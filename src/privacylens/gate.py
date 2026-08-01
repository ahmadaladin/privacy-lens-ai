"""CI gate for batch completeness and evidence consistency."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from privacylens.batch import BATCH_MANIFEST_SCHEMA_VERSION, DATASET_RISK_SUMMARY_NAME
from privacylens.pipeline import SUPPORTED_SUFFIXES
from privacylens.risk_summary import DatasetRiskSummary, load_risk_summary

MAX_BATCH_MANIFEST_BYTES = 5 * 1024 * 1024
MAX_QUARANTINE_RECORD_BYTES = 64 * 1024
_BATCH_KEYS = {
    "schema_version",
    "processing_mode",
    "processor",
    "risk_summary_path",
    "processed_count",
    "failed_count",
    "items",
}
_ITEM_KEYS = {
    "input_name",
    "status",
    "output_path",
    "manifest_path",
    "error_type",
    "error_message",
}


class BatchEvidenceError(ValueError):
    """Raised when batch evidence is missing, unsafe, or contradictory."""


@dataclass(frozen=True, slots=True)
class GateReport:
    """Value-free result suitable for logs and CI decisions."""

    completion_status: Literal["empty", "complete", "partial", "failed"]
    candidate_count: int
    processed_count: int
    failed_count: int

    @property
    def passed(self) -> bool:
        return self.completion_status == "complete" and self.candidate_count > 0


def verify_batch_output(output_dir: str | Path) -> GateReport:
    """Verify batch evidence and artifact presence without opening output images."""

    root = Path(output_dir)
    if not root.is_dir():
        raise BatchEvidenceError("batch output directory is unavailable")

    batch = _load_json(root / "batch-manifest.json", limit=MAX_BATCH_MANIFEST_BYTES)
    if set(batch) != _BATCH_KEYS:
        raise BatchEvidenceError("batch manifest has unsupported fields")
    if batch["schema_version"] != BATCH_MANIFEST_SCHEMA_VERSION:
        raise BatchEvidenceError("batch manifest schema is unsupported")
    if batch["risk_summary_path"] != DATASET_RISK_SUMMARY_NAME:
        raise BatchEvidenceError("risk-summary reference is unsafe")

    summary = _load_summary(root)
    _verify_batch_header(batch, summary)
    items = batch["items"]
    if not isinstance(items, list):
        raise BatchEvidenceError("batch items must be a list")

    seen_names: set[str] = set()
    expected_outputs: set[str] = set()
    expected_manifests: set[str] = set()
    expected_quarantine: set[str] = set()
    processed = 0
    failed = 0
    for item in items:
        if not isinstance(item, dict) or set(item) != _ITEM_KEYS:
            raise BatchEvidenceError("batch item has unsupported fields")
        name = _safe_leaf_name(item["input_name"])
        if name in seen_names:
            raise BatchEvidenceError("batch item names must be unique")
        seen_names.add(name)
        if item["status"] == "processed":
            _verify_processed_item(root, item, name)
            expected_outputs.add(name)
            expected_manifests.add(f"{name}.json")
            processed += 1
        elif item["status"] == "failed":
            _verify_failed_item(root, item, name)
            expected_quarantine.add(f"{name}.error.json")
            failed += 1
        else:
            raise BatchEvidenceError("batch item status is invalid")

    if processed != summary.processed_count or failed != summary.failed_count:
        raise BatchEvidenceError("batch item totals disagree with the risk summary")
    if len(items) != summary.candidate_count:
        raise BatchEvidenceError("batch candidate total is inconsistent")
    _verify_inventory(root, "sanitized", expected_outputs)
    _verify_inventory(root, "manifests", expected_manifests)
    _verify_inventory(root, "quarantine", expected_quarantine)
    return GateReport(
        completion_status=summary.completion_status,
        candidate_count=summary.candidate_count,
        processed_count=summary.processed_count,
        failed_count=summary.failed_count,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="privacy-lens-gate",
        description="Validate PrivacyLens batch evidence for CI.",
    )
    parser.add_argument("output_directory", help="PrivacyLens batch output directory")
    args = parser.parse_args(argv)
    try:
        report = verify_batch_output(args.output_directory)
    except (BatchEvidenceError, ValueError) as error:
        print(f"PrivacyLens gate: INVALID ({error})")
        return 2

    print(
        "PrivacyLens gate: "
        f"{report.completion_status.upper()} "
        f"(candidates={report.candidate_count}, "
        f"processed={report.processed_count}, failed={report.failed_count})"
    )
    return 0 if report.passed else 1


def _load_summary(root: Path) -> DatasetRiskSummary:
    try:
        return load_risk_summary(root / DATASET_RISK_SUMMARY_NAME)
    except ValueError as error:
        raise BatchEvidenceError("risk summary is invalid") from error


def _verify_batch_header(batch: dict[str, object], summary: DatasetRiskSummary) -> None:
    if not _is_non_negative_integer(batch["processed_count"]):
        raise BatchEvidenceError("processed total must be a non-negative integer")
    if not _is_non_negative_integer(batch["failed_count"]):
        raise BatchEvidenceError("failed total must be a non-negative integer")
    if batch["processing_mode"] != summary.processing_mode:
        raise BatchEvidenceError("processing modes disagree")
    if batch["processor"] != summary.processor:
        raise BatchEvidenceError("processor identifiers disagree")
    if batch["processed_count"] != summary.processed_count:
        raise BatchEvidenceError("processed totals disagree")
    if batch["failed_count"] != summary.failed_count:
        raise BatchEvidenceError("failed totals disagree")


def _verify_processed_item(root: Path, item: dict[str, object], name: str) -> None:
    expected_output = f"sanitized/{name}"
    expected_manifest = f"manifests/{name}.json"
    if item["output_path"] != expected_output or item["manifest_path"] != expected_manifest:
        raise BatchEvidenceError("processed artifact reference is unsafe")
    if item["error_type"] is not None or item["error_message"] is not None:
        raise BatchEvidenceError("processed item contains failure fields")
    _require_contained_file(root, expected_output, description="processed artifact")
    _require_contained_file(root, expected_manifest, description="processed artifact")


def _verify_failed_item(root: Path, item: dict[str, object], name: str) -> None:
    if item["output_path"] is not None or item["manifest_path"] is not None:
        raise BatchEvidenceError("failed item claims processed artifacts")
    if not _short_printable(item["error_type"], limit=128):
        raise BatchEvidenceError("failed item error type is invalid")
    if not _short_text(item["error_message"], limit=1024):
        raise BatchEvidenceError("failed item error message is invalid")
    quarantine_path = _require_contained_file(
        root,
        f"quarantine/{name}.error.json",
        description="quarantine record",
    )
    quarantine = _load_json(quarantine_path, limit=MAX_QUARANTINE_RECORD_BYTES)
    if quarantine != item:
        raise BatchEvidenceError("quarantine record disagrees with the batch manifest")


def _safe_leaf_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 255
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or not value.isprintable()
        or Path(value).suffix.lower() not in SUPPORTED_SUFFIXES
    ):
        raise BatchEvidenceError("batch item name is unsafe")
    return value


def _short_printable(value: object, *, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value) <= limit and value.isprintable()


def _short_text(value: object, *, limit: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and all(character.isprintable() or character in "\n\r\t" for character in value)
    )


def _is_non_negative_integer(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _require_contained_file(root: Path, relative: str, *, description: str) -> Path:
    candidate = root / relative
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except OSError as error:
        raise BatchEvidenceError(f"{description} is missing") from error
    if resolved_root not in resolved_candidate.parents:
        raise BatchEvidenceError(f"{description} escapes the output directory")
    if not resolved_candidate.is_file():
        raise BatchEvidenceError(f"{description} is missing")
    return resolved_candidate


def _verify_inventory(root: Path, directory_name: str, expected_names: set[str]) -> None:
    directory = root / directory_name
    if not directory.exists():
        if expected_names:
            raise BatchEvidenceError("expected artifact directory is missing")
        return
    try:
        resolved_root = root.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise BatchEvidenceError("artifact directory cannot be inspected") from error
    if resolved_root not in resolved_directory.parents or not resolved_directory.is_dir():
        raise BatchEvidenceError("artifact directory is unsafe")
    if any(not entry.is_file() for entry in entries):
        raise BatchEvidenceError("artifact directory contains an unsupported entry")
    if {entry.name for entry in entries} != expected_names:
        raise BatchEvidenceError("artifact inventory disagrees with the batch manifest")


def _load_json(path: Path, *, limit: int) -> dict[str, object]:
    try:
        if path.stat().st_size > limit:
            raise BatchEvidenceError("evidence file exceeds the safety limit")
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except OSError as error:
        raise BatchEvidenceError("required evidence file is unavailable") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BatchEvidenceError("evidence file must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise BatchEvidenceError("evidence file must contain a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BatchEvidenceError("evidence JSON contains duplicate keys")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
