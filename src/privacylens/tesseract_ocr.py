"""Local Tesseract adapter for provider-neutral OCR observations."""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from privacylens.models import BoundingBox
from privacylens.ocr import OCRExtraction, OCRObservation, OCRSidecar

DEFAULT_OCR_TIMEOUT_SECONDS = 30.0
MAX_TESSERACT_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_TESSERACT_WORDS = 50_000
LANGUAGE_PATTERN = re.compile(r"[a-z0-9_]{2,16}(?:\+[a-z0-9_]{2,16})*")
VERSION_PATTERN = re.compile(r"tesseract\s+([0-9]+(?:\.[0-9]+){1,3})", re.IGNORECASE)
TSV_COLUMNS = {
    "level",
    "page_num",
    "block_num",
    "par_num",
    "line_num",
    "word_num",
    "left",
    "top",
    "width",
    "height",
    "conf",
    "text",
}


@dataclass(frozen=True, slots=True)
class _Word:
    number: int
    text: str
    box: BoundingBox
    score: float | None


@dataclass(frozen=True, slots=True)
class TesseractOCR:
    """Execute an installed Tesseract binary and keep extracted text in memory."""

    language: str = "eng"
    timeout_seconds: float = DEFAULT_OCR_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.language, str) or not LANGUAGE_PATTERN.fullmatch(self.language):
            raise ValueError(
                "OCR language must use trained-data identifiers such as eng or eng+ara"
            )
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < self.timeout_seconds <= 300
        ):
            raise ValueError("OCR timeout must be greater than 0 and at most 300 seconds")

    def extract(self, source: Path, *, input_sha256: str) -> OCRExtraction:
        """Run local OCR and return line observations without writing a text sidecar."""

        executable = shutil.which("tesseract")
        if executable is None:
            raise FileNotFoundError(
                "Tesseract executable was not found; install Tesseract OCR and retry"
            )
        version = _read_version(executable)
        command = [
            executable,
            str(source.resolve()),
            "stdout",
            "-l",
            self.language,
            "tsv",
        ]
        completed = _run(command, timeout_seconds=float(self.timeout_seconds))
        if completed.returncode != 0:
            raise ValueError(f"Tesseract OCR failed with exit code {completed.returncode}")
        if len(completed.stdout) > MAX_TESSERACT_OUTPUT_BYTES:
            raise ValueError(
                f"Tesseract OCR output exceeds the {MAX_TESSERACT_OUTPUT_BYTES}-byte limit"
            )
        sidecar = parse_tesseract_tsv(completed.stdout, input_sha256=input_sha256)
        return OCRExtraction(
            sidecar=sidecar,
            engine="tesseract",
            engine_version=version,
            languages=tuple(self.language.split("+")),
        )


def parse_tesseract_tsv(raw_tsv: bytes, *, input_sha256: str) -> OCRSidecar:
    """Parse Tesseract word rows into deterministic, line-level observations."""

    if len(raw_tsv) > MAX_TESSERACT_OUTPUT_BYTES:
        raise ValueError(
            f"Tesseract OCR output exceeds the {MAX_TESSERACT_OUTPUT_BYTES}-byte limit"
        )
    try:
        text = raw_tsv.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Tesseract OCR output is not valid UTF-8") from error

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        if reader.fieldnames is None or not TSV_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("Tesseract OCR output is missing required TSV columns")
        grouped: dict[tuple[int, int, int, int], list[_Word]] = defaultdict(list)
        word_count = 0
        for row_number, row in enumerate(reader, start=2):
            level = _parse_int(row.get("level"), row_number=row_number)
            if level != 5:
                continue
            word_count += 1
            if word_count > MAX_TESSERACT_WORDS:
                raise ValueError(
                    f"Tesseract OCR output exceeds the {MAX_TESSERACT_WORDS}-word limit"
                )
            word = _parse_word(row, row_number=row_number)
            if word is None:
                continue
            key_values = (
                _parse_int(row.get("page_num"), row_number=row_number),
                _parse_int(row.get("block_num"), row_number=row_number),
                _parse_int(row.get("par_num"), row_number=row_number),
                _parse_int(row.get("line_num"), row_number=row_number),
            )
            if any(value <= 0 for value in key_values):
                raise ValueError(
                    f"Tesseract OCR output has invalid line identifiers on TSV row {row_number}"
                )
            key = key_values
            if any(existing.number == word.number for existing in grouped[key]):
                raise ValueError(
                    f"Tesseract OCR output has a duplicate word number on TSV row {row_number}"
                )
            grouped[key].append(word)
    except csv.Error as error:
        raise ValueError("Tesseract OCR output is malformed TSV") from error

    observations = tuple(_line_observation(words) for _, words in sorted(grouped.items()) if words)
    return OCRSidecar(input_sha256=input_sha256, observations=observations)


def _parse_word(row: dict[str, str | None], *, row_number: int) -> _Word | None:
    text = row.get("text")
    if text is None:
        raise ValueError(f"Tesseract OCR output is malformed on TSV row {row_number}")
    text = text.strip()
    if not text:
        return None

    left = _parse_int(row.get("left"), row_number=row_number)
    top = _parse_int(row.get("top"), row_number=row_number)
    width = _parse_int(row.get("width"), row_number=row_number)
    height = _parse_int(row.get("height"), row_number=row_number)
    if left < 0 or top < 0 or width <= 0 or height <= 0:
        raise ValueError(f"Tesseract OCR output has invalid coordinates on TSV row {row_number}")
    confidence = _parse_float(row.get("conf"), row_number=row_number)
    if confidence < -1 or confidence > 100:
        raise ValueError(f"Tesseract OCR output has invalid confidence on TSV row {row_number}")
    word_number = _parse_int(row.get("word_num"), row_number=row_number)
    if word_number <= 0:
        raise ValueError(f"Tesseract OCR output has an invalid word number on TSV row {row_number}")
    return _Word(
        number=word_number,
        text=text,
        box=BoundingBox(left, top, left + width, top + height),
        score=None if confidence < 0 else confidence / 100,
    )


def _line_observation(words: list[_Word]) -> OCRObservation:
    ordered = sorted(words, key=lambda word: word.number)
    scores = [word.score for word in ordered if word.score is not None]
    return OCRObservation(
        text=" ".join(word.text for word in ordered),
        box=BoundingBox(
            min(word.box.x1 for word in ordered),
            min(word.box.y1 for word in ordered),
            max(word.box.x2 for word in ordered),
            max(word.box.y2 for word in ordered),
        ),
        score=sum(scores) / len(scores) if scores else None,
    )


def _read_version(executable: str) -> str:
    completed = _run([executable, "--version"], timeout_seconds=5.0)
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise ValueError("could not determine the installed Tesseract version")
    match = VERSION_PATTERN.search(completed.stdout.decode("utf-8", errors="replace"))
    if match is None:
        raise ValueError("could not determine the installed Tesseract version")
    return match.group(1)


def _run(command: list[str], *, timeout_seconds: float) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        message = f"Tesseract OCR exceeded the {timeout_seconds:g}-second timeout"
        raise ValueError(message) from error


def _parse_int(value: str | None, *, row_number: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Tesseract OCR output has an invalid integer on TSV row {row_number}"
        ) from error


def _parse_float(value: str | None, *, row_number: int) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Tesseract OCR output has an invalid number on TSV row {row_number}"
        ) from error
