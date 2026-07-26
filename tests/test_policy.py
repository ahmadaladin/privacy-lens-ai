import json
from pathlib import Path

import pytest

from privacylens.policy import RedactionPolicy, load_policy


def test_default_policy_fails_closed_for_unscored_findings() -> None:
    outcome = RedactionPolicy().evaluate("email", None)

    assert outcome.action == "redact"
    assert outcome.reason == "unscored_fail_closed"


def test_policy_applies_kind_score_and_unscored_rules() -> None:
    policy = RedactionPolicy(
        redact_kinds=frozenset({"email", "phone"}),
        minimum_score=0.8,
        unscored_action="retain",
    )

    assert policy.evaluate("email", 0.91).reason == "policy_match"
    assert policy.evaluate("phone", 0.79).reason == "below_minimum_score"
    assert policy.evaluate("phone", None).reason == "unscored_retained"
    assert policy.evaluate("face", 0.99).reason == "kind_not_selected"


def test_load_policy_rejects_unknown_keys_and_kinds(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "redact_kinds": ["emali"],
                "silent_typo": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown policy key"):
        load_policy(policy_path, allowed_kinds=frozenset({"email", "phone"}))

    policy_path.write_text(
        json.dumps({"schema_version": "1.0", "redact_kinds": ["emali"]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported redact kind"):
        load_policy(policy_path, allowed_kinds=frozenset({"email", "phone"}))


@pytest.mark.parametrize(
    "minimum_score",
    [-0.01, 1.01, True, "0.8", float("nan")],
)
def test_policy_rejects_invalid_thresholds(minimum_score: object) -> None:
    with pytest.raises(ValueError):
        RedactionPolicy(minimum_score=minimum_score)  # type: ignore[arg-type]


def test_policy_rejects_string_instead_of_kind_collection() -> None:
    with pytest.raises(ValueError, match="collection"):
        RedactionPolicy(redact_kinds="email")  # type: ignore[arg-type]


def test_load_policy_requires_supported_schema(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text('{"schema_version": "2.0"}', encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version"):
        load_policy(policy_path)
