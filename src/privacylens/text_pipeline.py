"""Local text-file PII detection, redaction, and audit reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from privacylens.text_recognition import (
    CompositeTextRecognizer,
    TextDetection,
    TextRecognizer,
    redact_text,
)

TEXT_MANIFEST_SCHEMA_VERSION = "1.0"
MAX_TEXT_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TextProcessResult:
    """Result metadata that excludes original PII values and absolute paths."""

    input_name: str
    output_name: str
    recognizer: str
    detections: tuple[TextDetection, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": TEXT_MANIFEST_SCHEMA_VERSION,
            "input_name": self.input_name,
            "output_name": self.output_name,
            "recognizer": self.recognizer,
            "detections": [detection.to_dict() for detection in self.detections],
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
) -> TextProcessResult:
    """Detect and redact supported PII patterns in a UTF-8 text file."""

    source = Path(input_path)
    destination = Path(output_path)
    _validate_text_paths(source, destination)
    text = _read_text(source)
    active_recognizer = recognizer or CompositeTextRecognizer()
    detections = tuple(active_recognizer.detect(text))
    sanitized = redact_text(text, detections)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(sanitized, encoding="utf-8")

    return TextProcessResult(
        input_name=source.name,
        output_name=destination.name,
        recognizer=type(active_recognizer).__name__,
        detections=detections,
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
