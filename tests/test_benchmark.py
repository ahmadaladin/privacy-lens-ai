import json
from pathlib import Path

import pytest

from privacylens.benchmark import (
    BenchmarkCase,
    SyntheticTextBenchmark,
    evaluate_benchmark,
    load_benchmark,
    main,
)
from privacylens.text_recognition import TextDetection

FIXTURE = Path(__file__).parents[1] / "benchmarks" / "synthetic_text_v1.json"


class OffByOneRecognizer:
    def detect(self, text: str) -> list[TextDetection]:
        return [TextDetection("email", 0, 4)]


def test_versioned_multilingual_fixture_passes_exact_span_thresholds() -> None:
    benchmark = load_benchmark(FIXTURE)

    report = evaluate_benchmark(
        benchmark,
        minimum_precision=1.0,
        minimum_recall=1.0,
    )

    assert report.passed is True
    assert report.case_count == 8
    assert report.language_count == 2
    assert report.overall.to_dict() == {
        "expected_count": 6,
        "predicted_count": 6,
        "true_positive": 6,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
    }
    assert dict(report.by_language)["ar"].expected_count == 2
    assert dict(report.by_kind)["email"].expected_count == 3
    assert dict(report.by_kind)["phone"].expected_count == 3


def test_report_is_aggregate_only_and_excludes_synthetic_values(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"

    assert (
        main(
            [
                str(FIXTURE),
                str(report_path),
                "--minimum-precision",
                "1",
                "--minimum-recall",
                "1",
            ]
        )
        == 0
    )

    report_text = report_path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["passed"] is True
    assert report["evaluation_scope"] == ("text_pii_recognition_only_not_ocr_or_end_to_end_privacy")
    assert report["matching_strategy"] == "exact_kind_and_character_span"
    assert "fake.person@example.com" not in report_text
    assert "+١ ٢٠٢ ٥٥٥ ٠١٤٨" not in report_text
    assert "text" not in report
    assert "cases" not in report


def test_threshold_failure_returns_one_and_still_writes_report(tmp_path: Path) -> None:
    benchmark_path = tmp_path / "miss.json"
    report_path = tmp_path / "report.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "data_classification": "synthetic",
                "benchmark_id": "deliberate-miss",
                "cases": [
                    {
                        "case_id": "short-phone",
                        "language": "en",
                        "text": "Code 123",
                        "expected": [{"kind": "phone", "span": [5, 8]}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            str(benchmark_path),
            str(report_path),
            "--minimum-precision",
            "0.9",
            "--minimum-recall",
            "0.9",
        ]
    )

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["overall"]["false_negative"] == 1
    assert report["overall"]["precision"] is None
    assert report["overall"]["recall"] == 0.0


def test_exact_span_mismatch_counts_as_false_positive_and_false_negative() -> None:
    case = BenchmarkCase(
        case_id="boundary-mismatch",
        language="en",
        text="abcde",
        expected=(TextDetection("email", 0, 3),),
    )
    benchmark = SyntheticTextBenchmark(benchmark_id="boundary-test", cases=(case,))

    report = evaluate_benchmark(
        benchmark,
        minimum_precision=0.5,
        minimum_recall=0.5,
        recognizer=OffByOneRecognizer(),
    )

    assert report.passed is False
    assert report.overall.true_positive == 0
    assert report.overall.false_positive == 1
    assert report.overall.false_negative == 1
    assert report.overall.f1 == 0.0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"data_classification": "production"}, "classified as synthetic"),
        ({"unexpected": True}, "exactly the supported fields"),
        ({"schema_version": "2.0"}, "unsupported benchmark"),
    ],
)
def test_loader_rejects_unsafe_or_unknown_top_level_contracts(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data.update(change)
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_benchmark(path)


def test_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "benchmark.json"
    path.write_text(
        '{"schema_version":"1.0","schema_version":"1.0",'
        '"data_classification":"synthetic","benchmark_id":"duplicate",'
        '"cases":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate keys"):
        load_benchmark(path)


@pytest.mark.parametrize(
    ("field_path", "value", "message"),
    [
        (("benchmark_id",), 123, "benchmark_id"),
        (("cases", 0, "case_id"), 123, "case_id"),
        (("cases", 0, "language"), 123, "language"),
        (("cases", 0, "expected", 0, "kind"), ["email"], "kind must be a string"),
    ],
)
def test_loader_rejects_type_confusion(
    tmp_path: Path,
    field_path: tuple[object, ...],
    value: object,
    message: str,
) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    target = data
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = value
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_benchmark(path)


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ((TextDetection("phone", 0, 20),), "outside"),
        (
            (
                TextDetection("email", 0, 3),
                TextDetection("phone", 2, 4),
            ),
            "overlap",
        ),
        ((TextDetection("name", 0, 3),), "unsupported"),
    ],
)
def test_case_rejects_invalid_ground_truth(
    expected: tuple[TextDetection, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        BenchmarkCase(case_id="invalid", language="en", text="test", expected=expected)


def test_benchmark_rejects_duplicate_case_ids() -> None:
    case = BenchmarkCase(
        case_id="same",
        language="en",
        text="a@example.com",
        expected=(TextDetection("email", 0, 13),),
    )

    with pytest.raises(ValueError, match="unique"):
        SyntheticTextBenchmark(benchmark_id="duplicate-cases", cases=(case, case))


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), True])
def test_thresholds_must_be_finite_probabilities(threshold: object) -> None:
    benchmark = load_benchmark(FIXTURE)

    with pytest.raises(ValueError, match="between 0 and 1"):
        evaluate_benchmark(
            benchmark,
            minimum_precision=threshold,
            minimum_recall=0.9,
        )


def test_benchmark_cannot_overwrite_its_source(tmp_path: Path) -> None:
    source = tmp_path / "benchmark.json"
    source.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    assert (
        main(
            [
                str(source),
                str(source),
                "--minimum-precision",
                "0.9",
                "--minimum-recall",
                "0.9",
            ]
        )
        == 2
    )
