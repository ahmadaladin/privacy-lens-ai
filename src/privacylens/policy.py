"""Versioned, auditable redaction policy decisions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

POLICY_SCHEMA_VERSION = "1.0"
MAX_POLICY_BYTES = 64 * 1024
UNSCORED_ACTIONS = frozenset({"redact", "retain"})

PolicyAction = Literal["redact", "retain"]


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    """An auditable decision that does not contain the matched value."""

    action: PolicyAction
    reason: str


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Decide whether a finding should be redacted or retained."""

    redact_kinds: frozenset[str] | None = None
    minimum_score: float | None = None
    unscored_action: PolicyAction = "redact"

    def __post_init__(self) -> None:
        if self.redact_kinds is not None:
            if isinstance(self.redact_kinds, str):
                raise ValueError("redact_kinds must be a collection of kind names")
            normalized_kinds = frozenset(self.redact_kinds)
            if not normalized_kinds or any(
                not isinstance(kind, str) or not kind for kind in normalized_kinds
            ):
                raise ValueError("redact_kinds must contain at least one non-empty kind")
            object.__setattr__(self, "redact_kinds", normalized_kinds)
        if self.minimum_score is not None:
            minimum_score = _validated_score(self.minimum_score, name="minimum_score")
            object.__setattr__(self, "minimum_score", minimum_score)
        if self.unscored_action not in UNSCORED_ACTIONS:
            raise ValueError("unscored_action must be 'redact' or 'retain'")

    def evaluate(self, kind: str, score: float | None) -> PolicyOutcome:
        """Return a deterministic decision and machine-readable reason."""

        if score is not None:
            score = _validated_score(score, name="finding score")
        if self.redact_kinds is not None and kind not in self.redact_kinds:
            return PolicyOutcome("retain", "kind_not_selected")
        if score is None:
            if self.unscored_action == "redact":
                return PolicyOutcome("redact", "unscored_fail_closed")
            return PolicyOutcome("retain", "unscored_retained")
        if self.minimum_score is not None and score < self.minimum_score:
            return PolicyOutcome("retain", "below_minimum_score")
        return PolicyOutcome("redact", "policy_match")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": POLICY_SCHEMA_VERSION,
            "redact_kinds": (None if self.redact_kinds is None else sorted(self.redact_kinds)),
            "minimum_score": self.minimum_score,
            "unscored_action": self.unscored_action,
        }


def load_policy(
    path: str | Path,
    *,
    allowed_kinds: frozenset[str] | None = None,
) -> RedactionPolicy:
    """Load a small, strict JSON policy without accepting silent typos."""

    policy_path = Path(path)
    if not policy_path.is_file():
        raise FileNotFoundError(f"policy file does not exist: {policy_path.name}")
    if policy_path.suffix.lower() != ".json":
        raise ValueError("policy file must use the .json extension")
    if policy_path.stat().st_size > MAX_POLICY_BYTES:
        raise ValueError(f"policy file exceeds the {MAX_POLICY_BYTES}-byte safety limit")

    data = _read_json(policy_path)
    allowed_keys = {
        "schema_version",
        "redact_kinds",
        "minimum_score",
        "unscored_action",
    }
    unknown_keys = set(data) - allowed_keys
    if unknown_keys:
        raise ValueError(f"unknown policy key: {sorted(unknown_keys)[0]}")
    if data.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError(f"policy schema_version must be {POLICY_SCHEMA_VERSION}")

    redact_kinds = _parse_kinds(data.get("redact_kinds"), allowed_kinds)
    minimum_score = _parse_score(data.get("minimum_score"))
    unscored_action = data.get("unscored_action", "redact")
    if not isinstance(unscored_action, str) or unscored_action not in UNSCORED_ACTIONS:
        raise ValueError("unscored_action must be 'redact' or 'retain'")

    return RedactionPolicy(
        redact_kinds=redact_kinds,
        minimum_score=minimum_score,
        unscored_action=unscored_action,
    )


def _read_json(path: Path) -> dict[str, object]:
    try:
        raw_data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"policy file is not valid UTF-8: {path.name}") from error
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as error:
        raise ValueError(f"policy file is not valid JSON: {path.name}") from error
    if not isinstance(data, dict):
        raise ValueError("policy JSON must contain an object")
    return data


def _parse_kinds(
    value: object,
    allowed_kinds: frozenset[str] | None,
) -> frozenset[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ValueError("redact_kinds must be a non-empty list")
    if any(not isinstance(kind, str) or not kind for kind in value):
        raise ValueError("each redact_kinds entry must be a non-empty string")
    if len(set(value)) != len(value):
        raise ValueError("redact_kinds must not contain duplicates")
    kinds = frozenset(value)
    if allowed_kinds is not None:
        unsupported = kinds - allowed_kinds
        if unsupported:
            raise ValueError(f"unsupported redact kind: {sorted(unsupported)[0]}")
    return kinds


def _parse_score(value: object) -> float | None:
    if value is None:
        return None
    return _validated_score(value, name="minimum_score")


def _validated_score(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number between 0 and 1")
    score = float(value)
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return score
