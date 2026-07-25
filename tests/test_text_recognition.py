import pytest

from privacylens.text_recognition import (
    CompositeTextRecognizer,
    TextDetection,
    redact_text,
)


def test_composite_recognizer_redacts_email_and_phone_without_scores() -> None:
    source = "Contact demo.person+qa@example.com or +60 (12) 345-6789."

    detections = CompositeTextRecognizer().detect(source)
    sanitized = redact_text(source, detections)

    assert [detection.kind for detection in detections] == ["email", "phone"]
    assert all(detection.score is None for detection in detections)
    assert sanitized == "Contact [EMAIL] or [PHONE]."


def test_phone_recognizer_accepts_unicode_decimal_digits() -> None:
    source = "Arabic digits: +٦٠ ١٢ ٣٤٥ ٦٧٨٩"

    detections = CompositeTextRecognizer().detect(source)

    assert [detection.kind for detection in detections] == ["phone"]
    assert redact_text(source, detections) == "Arabic digits: [PHONE]"


def test_email_priority_prevents_overlapping_phone_detection() -> None:
    source = "Use 123456789@example.com."

    detections = CompositeTextRecognizer().detect(source)

    assert [detection.kind for detection in detections] == ["email"]
    assert redact_text(source, detections) == "Use [EMAIL]."


def test_date_is_not_treated_as_phone_number() -> None:
    source = "Review date: 2026-07-25."

    assert CompositeTextRecognizer().detect(source) == []


@pytest.mark.parametrize(
    "detections",
    [
        [TextDetection(kind="email", start=-1, end=2)],
        [TextDetection(kind="email", start=0, end=20)],
        [
            TextDetection(kind="email", start=0, end=3),
            TextDetection(kind="phone", start=2, end=4),
        ],
    ],
)
def test_redaction_rejects_unsafe_spans(detections: list[TextDetection]) -> None:
    with pytest.raises(ValueError):
        redact_text("test", detections)
