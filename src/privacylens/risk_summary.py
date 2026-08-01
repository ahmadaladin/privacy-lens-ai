"""Privacy-safe operational summaries for processed datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RISK_SUMMARY_SCHEMA_VERSION = "1.0"
RISK_SUMMARY_INTERPRETATION = "operational_counts_only_not_accuracy_or_safety_metrics"
MAX_RISK_SUMMARY_BYTES = 64 * 1024
CompletionStatus = Literal["empty", "complete", "partial", "failed"]
ProcessingMode = Literal["detector", "ocr"]


@dataclass(frozen=True, slots=True)
class DatasetRiskSummary:
    """Aggregate value-free findings without source identifiers."""

    processing_mode: ProcessingMode
    processor: str
    candidate_count: int
    processed_count: int
    failed_count: int
    images_with_findings: int
    images_without_findings: int
    total_findings: int
    findings_by_kind: tuple[tuple[str, int], ...]
    ocr_observation_count: int | None

    def __post_init__(self) -> None:
        counts = (
            self.candidate_count,
            self.processed_count,
            self.failed_count,
            self.images_with_findings,
            self.images_without_findings,
            self.total_findings,
        )
        if any(
            isinstance(count, bool) or not isinstance(count, int) or count < 0 for count in counts
        ):
            raise ValueError("risk-summary counts must be non-negative integers")
        if self.processing_mode not in {"detector", "ocr"}:
            raise ValueError("risk-summary processing_mode must be detector or ocr")
        if (
            not isinstance(self.processor, str)
            or not self.processor
            or len(self.processor) > 128
            or not self.processor.isprintable()
        ):
            raise ValueError("risk-summary processor must be a short printable identifier")
        if self.processed_count + self.failed_count != self.candidate_count:
            raise ValueError("processed and failed counts must equal candidate_count")
        if self.images_with_findings + self.images_without_findings != self.processed_count:
            raise ValueError("finding-image counts must equal processed_count")
        _validate_findings(self.findings_by_kind, total=self.total_findings)
        if self.processing_mode == "ocr":
            if (
                isinstance(self.ocr_observation_count, bool)
                or not isinstance(self.ocr_observation_count, int)
                or self.ocr_observation_count < 0
            ):
                raise ValueError("OCR summaries require a non-negative observation count")
        elif self.ocr_observation_count is not None:
            raise ValueError("detector summaries must not claim OCR observations")

    @property
    def completion_status(self) -> CompletionStatus:
        if self.candidate_count == 0:
            return "empty"
        if self.failed_count == 0:
            return "complete"
        if self.processed_count == 0:
            return "failed"
        return "partial"

    @property
    def processing_attention_required(self) -> bool:
        return self.completion_status != "complete"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": RISK_SUMMARY_SCHEMA_VERSION,
            "interpretation": RISK_SUMMARY_INTERPRETATION,
            "processing_mode": self.processing_mode,
            "processor": self.processor,
            "completion_status": self.completion_status,
            "processing_attention_required": self.processing_attention_required,
            "candidate_count": self.candidate_count,
            "processed_count": self.processed_count,
            "failed_count": self.failed_count,
            "images_with_findings": self.images_with_findings,
            "images_without_findings": self.images_without_findings,
            "total_findings": self.total_findings,
            "findings_by_kind": dict(self.findings_by_kind),
            "ocr_observation_count": self.ocr_observation_count,
        }

    def write(self, path: str | Path) -> None:
        summary_path = Path(path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load_risk_summary(path: str | Path) -> DatasetRiskSummary:
    """Load and strictly validate an untrusted dataset risk summary."""

    summary_path = Path(path)
    try:
        if summary_path.stat().st_size > MAX_RISK_SUMMARY_BYTES:
            raise ValueError("risk summary exceeds the safety limit")
        data = json.loads(
            summary_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except OSError as error:
        raise ValueError("risk summary cannot be read") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("risk summary must be valid UTF-8 JSON") from error

    expected_keys = {
        "schema_version",
        "interpretation",
        "processing_mode",
        "processor",
        "completion_status",
        "processing_attention_required",
        "candidate_count",
        "processed_count",
        "failed_count",
        "images_with_findings",
        "images_without_findings",
        "total_findings",
        "findings_by_kind",
        "ocr_observation_count",
    }
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("risk summary must contain exactly the supported fields")
    if data["schema_version"] != RISK_SUMMARY_SCHEMA_VERSION:
        raise ValueError("unsupported risk-summary schema_version")
    if data["interpretation"] != RISK_SUMMARY_INTERPRETATION:
        raise ValueError("risk-summary interpretation is invalid")
    findings = data["findings_by_kind"]
    if not isinstance(findings, dict):
        raise ValueError("findings_by_kind must be an object")

    try:
        summary = DatasetRiskSummary(
            processing_mode=data["processing_mode"],
            processor=data["processor"],
            candidate_count=data["candidate_count"],
            processed_count=data["processed_count"],
            failed_count=data["failed_count"],
            images_with_findings=data["images_with_findings"],
            images_without_findings=data["images_without_findings"],
            total_findings=data["total_findings"],
            findings_by_kind=tuple(sorted(findings.items())),
            ocr_observation_count=data["ocr_observation_count"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("risk summary contains invalid values") from error
    if summary.to_dict() != data:
        raise ValueError("risk summary contains inconsistent derived fields")
    return summary


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON objects must not contain duplicate keys")
        result[key] = value
    return result


def _validate_findings(findings: tuple[tuple[str, int], ...], *, total: int) -> None:
    if not isinstance(findings, tuple):
        raise ValueError("findings_by_kind must be an immutable tuple")
    previous_kind = ""
    counted_total = 0
    for entry in findings:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError("each findings_by_kind entry must contain kind and count")
        kind, count = entry
        if not isinstance(kind, str) or not kind or len(kind) > 64 or not kind.isprintable():
            raise ValueError("finding kind must be a short printable identifier")
        if kind <= previous_kind:
            raise ValueError("findings_by_kind must be uniquely sorted")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("finding counts must be positive integers")
        previous_kind = kind
        counted_total += count
    if counted_total != total:
        raise ValueError("findings_by_kind counts must equal total_findings")
