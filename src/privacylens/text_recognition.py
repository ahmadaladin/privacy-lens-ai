"""Explainable text PII recognizers that do not retain matched values."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])"
    r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+"
    r"(?![\w-])",
    re.IGNORECASE,
)
PHONE_CANDIDATE_PATTERN = re.compile(r"(?<!\w)\+?[\d(][\d\s().-]{7,}\d(?!\w)")
MIN_PHONE_DIGITS = 9
MAX_PHONE_DIGITS = 15


@dataclass(frozen=True, slots=True)
class TextDetection:
    """A character span containing a category of sensitive text."""

    kind: str
    start: int
    end: int
    score: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "score": None if self.score is None else round(float(self.score), 4),
            "span": [self.start, self.end],
        }


class TextRecognizer(Protocol):
    """Anything that locates sensitive spans in text."""

    def detect(self, text: str) -> list[TextDetection]:
        """Return sensitive spans without retaining their values."""
        ...


class EmailRecognizer:
    """Find conventional ASCII email addresses with an explainable rule."""

    def detect(self, text: str) -> list[TextDetection]:
        return [
            TextDetection(kind="email", start=match.start(), end=match.end())
            for match in EMAIL_PATTERN.finditer(text)
        ]


class PhoneRecognizer:
    """Find plausible international or local phone-number spans.

    This baseline accepts Unicode decimal digits and common separators. It is
    intentionally conservative about length but does not infer a country or
    claim that every match is a valid assigned number.
    """

    def detect(self, text: str) -> list[TextDetection]:
        detections: list[TextDetection] = []
        for match in PHONE_CANDIDATE_PATTERN.finditer(text):
            digit_count = sum(character.isdecimal() for character in match.group())
            if MIN_PHONE_DIGITS <= digit_count <= MAX_PHONE_DIGITS:
                detections.append(TextDetection(kind="phone", start=match.start(), end=match.end()))
        return detections


class CompositeTextRecognizer:
    """Combine recognizers in priority order and remove overlapping spans."""

    def __init__(self, recognizers: Sequence[TextRecognizer] | None = None) -> None:
        self._recognizers = tuple(
            recognizers if recognizers is not None else (EmailRecognizer(), PhoneRecognizer())
        )

    def detect(self, text: str) -> list[TextDetection]:
        accepted: list[TextDetection] = []
        for recognizer in self._recognizers:
            for detection in recognizer.detect(text):
                if not any(_overlaps(detection, existing) for existing in accepted):
                    accepted.append(detection)
        return sorted(accepted, key=lambda detection: (detection.start, detection.end))


def redact_text(text: str, detections: Iterable[TextDetection]) -> str:
    """Replace non-overlapping sensitive spans with category markers."""

    ordered = sorted(detections, key=lambda detection: (detection.start, detection.end))
    _validate_spans(text, ordered)

    result = text
    for detection in reversed(ordered):
        marker = f"[{detection.kind.upper()}]"
        result = result[: detection.start] + marker + result[detection.end :]
    return result


def _overlaps(first: TextDetection, second: TextDetection) -> bool:
    return first.start < second.end and second.start < first.end


def _validate_spans(text: str, detections: Sequence[TextDetection]) -> None:
    previous_end = 0
    for detection in detections:
        if detection.start < 0 or detection.end > len(text) or detection.start >= detection.end:
            raise ValueError("text detection span is outside the source text")
        if detection.start < previous_end:
            raise ValueError("text detection spans must not overlap")
        previous_end = detection.end
