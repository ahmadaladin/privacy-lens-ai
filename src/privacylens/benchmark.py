"""Synthetic text-PII benchmark evaluation with privacy-safe aggregate reports."""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from privacylens.text_recognition import (
    CompositeTextRecognizer,
    TextDetection,
    TextRecognizer,
)

BENCHMARK_SCHEMA_VERSION = "1.0"
BENCHMARK_REPORT_SCHEMA_VERSION = "1.0"
MAX_BENCHMARK_BYTES = 1024 * 1024
MAX_CASES = 500
MAX_CASE_TEXT_CHARACTERS = 10_000
MAX_TOTAL_TEXT_CHARACTERS = 500_000
SUPPORTED_KINDS = frozenset({"email", "phone"})
EVALUATION_SCOPE = "text_pii_recognition_only_not_ocr_or_end_to_end_privacy"
MATCHING_STRATEGY = "exact_kind_and_character_span"
_IDENTIFIER_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_LANGUAGE_PATTERN = re.compile(r"[a-z]{2,3}(?:-[A-Z]{2})?")


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One declared-synthetic text sample with exact-span ground truth."""

    case_id: str
    language: str
    text: str
    expected: tuple[TextDetection, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _IDENTIFIER_PATTERN.fullmatch(self.case_id):
            raise ValueError("case_id must be a short lowercase identifier")
        if not isinstance(self.language, str) or not _LANGUAGE_PATTERN.fullmatch(self.language):
            raise ValueError("language must be a short BCP 47-style identifier")
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("benchmark text must be a non-empty string")
        if len(self.text) > MAX_CASE_TEXT_CHARACTERS:
            raise ValueError("benchmark case text exceeds the safety limit")
        _validate_expected(self.text, self.expected)


@dataclass(frozen=True, slots=True)
class SyntheticTextBenchmark:
    """Versioned collection of synthetic recognizer-evaluation cases."""

    benchmark_id: str
    cases: tuple[BenchmarkCase, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark_id, str) or not _IDENTIFIER_PATTERN.fullmatch(
            self.benchmark_id
        ):
            raise ValueError("benchmark_id must be a short lowercase identifier")
        if not isinstance(self.cases, tuple) or not 1 <= len(self.cases) <= MAX_CASES:
            raise ValueError("benchmark must contain between 1 and 500 cases")
        if any(not isinstance(case, BenchmarkCase) for case in self.cases):
            raise ValueError("benchmark cases must use the BenchmarkCase model")
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("benchmark case_id values must be unique")
        if sum(len(case.text) for case in self.cases) > MAX_TOTAL_TEXT_CHARACTERS:
            raise ValueError("benchmark text exceeds the total safety limit")
        if not any(case.expected for case in self.cases):
            raise ValueError("benchmark must contain at least one expected finding")


@dataclass(frozen=True, slots=True)
class MetricResult:
    """Exact-match counts and derived metrics for one aggregate slice."""

    true_positive: int
    false_positive: int
    false_negative: int

    @property
    def predicted_count(self) -> int:
        return self.true_positive + self.false_positive

    @property
    def expected_count(self) -> int:
        return self.true_positive + self.false_negative

    @property
    def precision(self) -> float | None:
        return _ratio(self.true_positive, self.predicted_count)

    @property
    def recall(self) -> float | None:
        return _ratio(self.true_positive, self.expected_count)

    @property
    def f1(self) -> float | None:
        precision = self.precision
        recall = self.recall
        if precision is None or recall is None:
            return None
        if precision + recall == 0:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 6)

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_count": self.expected_count,
            "predicted_count": self.predicted_count,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate-only evaluation report that excludes text and spans."""

    benchmark_id: str
    recognizer: str
    case_count: int
    language_count: int
    minimum_precision: float
    minimum_recall: float
    overall: MetricResult
    by_kind: tuple[tuple[str, MetricResult], ...]
    by_language: tuple[tuple[str, MetricResult], ...]

    @property
    def passed(self) -> bool:
        return (
            self.overall.precision is not None
            and self.overall.recall is not None
            and self.overall.precision >= self.minimum_precision
            and self.overall.recall >= self.minimum_recall
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": BENCHMARK_REPORT_SCHEMA_VERSION,
            "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
            "evaluation_scope": EVALUATION_SCOPE,
            "data_classification": "synthetic_declared_not_verified",
            "matching_strategy": MATCHING_STRATEGY,
            "benchmark_id": self.benchmark_id,
            "recognizer": self.recognizer,
            "case_count": self.case_count,
            "language_count": self.language_count,
            "thresholds": {
                "minimum_precision": self.minimum_precision,
                "minimum_recall": self.minimum_recall,
            },
            "passed": self.passed,
            "overall": self.overall.to_dict(),
            "by_kind": {kind: metric.to_dict() for kind, metric in self.by_kind},
            "by_language": {language: metric.to_dict() for language, metric in self.by_language},
        }

    def write(self, path: str | Path) -> None:
        report_path = Path(path)
        if report_path.suffix.lower() != ".json":
            raise ValueError("benchmark report must use the .json extension")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load_benchmark(path: str | Path) -> SyntheticTextBenchmark:
    """Load a strict, size-bounded benchmark declared to contain synthetic data."""

    benchmark_path = Path(path)
    try:
        if benchmark_path.suffix.lower() != ".json":
            raise ValueError("benchmark must use the .json extension")
        if benchmark_path.stat().st_size > MAX_BENCHMARK_BYTES:
            raise ValueError("benchmark exceeds the safety limit")
        data = json.loads(
            benchmark_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except OSError as error:
        raise ValueError("benchmark cannot be read") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("benchmark must be valid UTF-8 JSON") from error

    expected_keys = {"schema_version", "data_classification", "benchmark_id", "cases"}
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("benchmark must contain exactly the supported fields")
    if data["schema_version"] != BENCHMARK_SCHEMA_VERSION:
        raise ValueError("unsupported benchmark schema_version")
    if data["data_classification"] != "synthetic":
        raise ValueError("benchmark must be explicitly classified as synthetic")
    raw_cases = data["cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("benchmark cases must be a list")

    cases = tuple(_parse_case(raw_case) for raw_case in raw_cases)
    return SyntheticTextBenchmark(benchmark_id=data["benchmark_id"], cases=cases)


def evaluate_benchmark(
    benchmark: SyntheticTextBenchmark,
    *,
    minimum_precision: float,
    minimum_recall: float,
    recognizer: TextRecognizer | None = None,
) -> BenchmarkReport:
    """Evaluate exact kind/span matches and return aggregate-only metrics."""

    precision_threshold = _validate_threshold(minimum_precision, name="minimum_precision")
    recall_threshold = _validate_threshold(minimum_recall, name="minimum_recall")
    active_recognizer = recognizer or CompositeTextRecognizer()
    expected: set[tuple[int, str, int, int]] = set()
    predicted: set[tuple[int, str, int, int]] = set()
    languages: dict[int, str] = {}

    for index, case in enumerate(benchmark.cases):
        languages[index] = case.language
        for detection in case.expected:
            expected.add((index, detection.kind, detection.start, detection.end))
        detections = active_recognizer.detect(case.text)
        _validate_expected(case.text, tuple(detections))
        for detection in detections:
            predicted.add((index, detection.kind, detection.start, detection.end))

    overall = _metrics(expected, predicted)
    by_kind = tuple(
        (
            kind,
            _metrics(
                {finding for finding in expected if finding[1] == kind},
                {finding for finding in predicted if finding[1] == kind},
            ),
        )
        for kind in sorted(SUPPORTED_KINDS)
    )
    language_names = sorted(set(languages.values()))
    by_language = tuple(
        (
            language,
            _metrics(
                {finding for finding in expected if languages[finding[0]] == language},
                {finding for finding in predicted if languages[finding[0]] == language},
            ),
        )
        for language in language_names
    )
    return BenchmarkReport(
        benchmark_id=benchmark.benchmark_id,
        recognizer=type(active_recognizer).__name__,
        case_count=len(benchmark.cases),
        language_count=len(language_names),
        minimum_precision=precision_threshold,
        minimum_recall=recall_threshold,
        overall=overall,
        by_kind=by_kind,
        by_language=by_language,
    )


def run_benchmark_file(
    benchmark_path: str | Path,
    report_path: str | Path,
    *,
    minimum_precision: float,
    minimum_recall: float,
) -> BenchmarkReport:
    source = Path(benchmark_path)
    destination = Path(report_path)
    if source.resolve() == destination.resolve():
        raise ValueError("benchmark and report paths must be different")
    report = evaluate_benchmark(
        load_benchmark(source),
        minimum_precision=minimum_precision,
        minimum_recall=minimum_recall,
    )
    report.write(destination)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="privacy-lens-benchmark",
        description="Evaluate text PII recognition on declared-synthetic labeled data.",
    )
    parser.add_argument("benchmark", help="versioned synthetic benchmark JSON")
    parser.add_argument("report", help="aggregate JSON report destination")
    parser.add_argument("--minimum-precision", required=True, type=float)
    parser.add_argument("--minimum-recall", required=True, type=float)
    args = parser.parse_args(argv)
    try:
        report = run_benchmark_file(
            args.benchmark,
            args.report,
            minimum_precision=args.minimum_precision,
            minimum_recall=args.minimum_recall,
        )
    except ValueError as error:
        print(f"PrivacyLens benchmark: INVALID ({error})")
        return 2
    status = "PASS" if report.passed else "FAIL"
    print(
        f"PrivacyLens benchmark: {status} "
        f"(cases={report.case_count}, precision={report.overall.precision}, "
        f"recall={report.overall.recall}, f1={report.overall.f1})"
    )
    return 0 if report.passed else 1


def _parse_case(raw_case: object) -> BenchmarkCase:
    if not isinstance(raw_case, dict) or set(raw_case) != {
        "case_id",
        "language",
        "text",
        "expected",
    }:
        raise ValueError("benchmark case must contain exactly the supported fields")
    raw_expected = raw_case["expected"]
    if not isinstance(raw_expected, list):
        raise ValueError("case expected findings must be a list")
    expected = tuple(_parse_expected(item) for item in raw_expected)
    return BenchmarkCase(
        case_id=raw_case["case_id"],
        language=raw_case["language"],
        text=raw_case["text"],
        expected=expected,
    )


def _parse_expected(raw_expected: object) -> TextDetection:
    if not isinstance(raw_expected, dict) or set(raw_expected) != {"kind", "span"}:
        raise ValueError("expected finding must contain kind and span")
    span = raw_expected["span"]
    if (
        not isinstance(span, list)
        or len(span) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in span)
    ):
        raise ValueError("expected span must contain two integers")
    if not isinstance(raw_expected["kind"], str):
        raise ValueError("expected finding kind must be a string")
    return TextDetection(kind=raw_expected["kind"], start=span[0], end=span[1])


def _validate_expected(text: str, detections: tuple[TextDetection, ...]) -> None:
    if not isinstance(detections, tuple):
        raise ValueError("expected findings must be immutable")
    if any(not isinstance(detection, TextDetection) for detection in detections):
        raise ValueError("findings must use the TextDetection model")
    ordered = sorted(detections, key=lambda detection: (detection.start, detection.end))
    previous_end = 0
    seen: set[tuple[str, int, int]] = set()
    for detection in ordered:
        if not isinstance(detection.kind, str) or detection.kind not in SUPPORTED_KINDS:
            raise ValueError("finding kind is unsupported by this benchmark")
        if (
            isinstance(detection.start, bool)
            or isinstance(detection.end, bool)
            or not isinstance(detection.start, int)
            or not isinstance(detection.end, int)
            or detection.start < 0
            or detection.end > len(text)
            or detection.start >= detection.end
        ):
            raise ValueError("finding span is outside the benchmark text")
        key = (detection.kind, detection.start, detection.end)
        if key in seen:
            raise ValueError("benchmark findings must not contain duplicates")
        if detection.start < previous_end:
            raise ValueError("benchmark findings must not overlap")
        seen.add(key)
        previous_end = detection.end


def _metrics(
    expected: set[tuple[int, str, int, int]],
    predicted: set[tuple[int, str, int, int]],
) -> MetricResult:
    return MetricResult(
        true_positive=len(expected & predicted),
        false_positive=len(predicted - expected),
        false_negative=len(expected - predicted),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _validate_threshold(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number between 0 and 1")
    threshold = float(value)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return threshold


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("benchmark JSON must not contain duplicate keys")
        result[key] = value
    return result


if __name__ == "__main__":
    raise SystemExit(main())
