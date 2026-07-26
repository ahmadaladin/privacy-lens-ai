"""Local text-file PII detection, redaction, and audit reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from privacylens.policy import PolicyAction, RedactionPolicy
from privacylens.text_recognition import (
    CompositeTextRecognizer,
    TextDetection,
    TextRecognizer,
    redact_text,
)

TEXT_MANIFEST_SCHEMA_VERSION = "1.1"
MAX_TEXT_BYTES = 5 * 1024 * 1024
TEXT_PII_KINDS = frozenset({"email", "phone"})


@dataclass(frozen=True, slots=True)
class TextPolicyDecision:
    """A value-free record of what the policy did with one finding."""

    detection: TextDetection
    action: PolicyAction
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            **self.detection.to_dict(),
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TextProcessResult:
    """Result metadata that excludes original PII values and absolute paths."""

    input_name: str
    output_name: str
    recognizer: str
    policy: RedactionPolicy
    decisions: tuple[TextPolicyDecision, ...]

    @property
    def detections(self) -> tuple[TextDetection, ...]:
        return tuple(decision.detection for decision in self.decisions)

    @property
    def redacted_count(self) -> int:
        return sum(decision.action == "redact" for decision in self.decisions)

    @property
    def retained_count(self) -> int:
        return len(self.decisions) - self.redacted_count

    @property
    def review_required(self) -> bool:
        return self.retained_count > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TEXT_MANIFEST_SCHEMA_VERSION,
            "input_name": self.input_name,
            "output_name": self.output_name,
            "recognizer": self.recognizer,
            "policy": self.policy.to_dict(),
            "redacted_count": self.redacted_count,
            "retained_count": self.retained_count,
            "review_required": self.review_required,
            "detections": [decision.to_dict() for decision in self.decisions],
        }

    def write_manifest(self, path: str | Path) -> None:
        manifest_path = Path(path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def process_text_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    recognizer: TextRecognizer | None = None,
    policy: RedactionPolicy | None = None,
) -> TextProcessResult:
    """Detect and redact supported PII patterns in a UTF-8 text file."""

    source = Path(input_path)
    destination = Path(output_path)
    _validate_text_paths(source, destination)
    text = _read_text(source)
    active_recognizer = recognizer or CompositeTextRecognizer()
    active_policy = policy or RedactionPolicy()
    detections = tuple(active_recognizer.detect(text))
    decisions: list[TextPolicyDecision] = []
    for detection in detections:
        outcome = active_policy.evaluate(detection.kind, detection.score)
        decisions.append(
            TextPolicyDecision(
                detection=detection,
                action=outcome.action,
                reason=outcome.reason,
            )
        )
    decision_tuple = tuple(decisions)
    sanitized = redact_text(
        text,
        (decision.detection for decision in decision_tuple if decision.action == "redact"),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(sanitized, encoding="utf-8")

    return TextProcessResult(
        input_name=source.name,
        output_name=destination.name,
        recognizer=type(active_recognizer).__name__,
        policy=active_policy,
        decisions=decision_tuple,
    )


def _validate_text_paths(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"input text file does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise ValueError("input and output paths must be different")
    if source.suffix.lower() != ".txt":
        raise ValueError(f"unsupported text input format: {source.suffix or '<none>'}")
    if destination.suffix.lower() != ".txt":
        raise ValueError(f"unsupported text output format: {destination.suffix or '<none>'}")
    if source.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError(f"text input exceeds the {MAX_TEXT_BYTES}-byte safety limit")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"text input is not valid UTF-8: {path.name}") from error
