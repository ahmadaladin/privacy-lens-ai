import subprocess
from pathlib import Path

import pytest

from privacylens.models import BoundingBox
from privacylens.tesseract_ocr import TesseractOCR, _run, parse_tesseract_tsv

VALID_SHA256 = "a" * 64
HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext\n"
)
VALID_TSV = (
    HEADER
    + "4\t1\t1\t1\t1\t0\t10\t20\t150\t20\t-1\t\n"
    + "5\t1\t1\t1\t1\t1\t10\t20\t25\t20\t90\t+60\n"
    + "5\t1\t1\t1\t1\t2\t40\t20\t55\t20\t80\t12-345\n"
    + "5\t1\t1\t1\t1\t3\t100\t20\t45\t20\t70\t6789\n"
    + "5\t1\t1\t1\t2\t1\t10\t60\t190\t20\t95\tfake.person@example.com\n"
)


def test_parse_tesseract_tsv_groups_words_into_lines_for_pii_mapping() -> None:
    sidecar = parse_tesseract_tsv(VALID_TSV.encode(), input_sha256=VALID_SHA256)

    assert [observation.text for observation in sidecar.observations] == [
        "+60 12-345 6789",
        "fake.person@example.com",
    ]
    assert sidecar.observations[0].box == BoundingBox(10, 20, 145, 40)
    assert sidecar.observations[0].score == pytest.approx(0.8)
    assert [detection.kind for detection in sidecar.pii_detections()] == [
        "phone",
        "email",
    ]


@pytest.mark.parametrize(
    ("raw_tsv", "message"),
    [
        (b"level\ttext\n5\tprivate@example.com\n", "missing required"),
        (
            (HEADER + "5\t1\t1\t1\t1\t1\t-1\t2\t4\t5\t90\tprivate@example.com\n").encode(),
            "invalid coordinates",
        ),
        (
            (HEADER + "5\t1\t1\t1\t1\t1\t1\t2\t4\t5\t101\tprivate@example.com\n").encode(),
            "invalid confidence",
        ),
        (
            (
                HEADER
                + "5\t1\t1\t1\t1\t1\t1\t2\t4\t5\t90\tprivate@example.com\n"
                + "5\t1\t1\t1\t1\t1\t6\t2\t4\t5\t90\tsecond@example.com\n"
            ).encode(),
            "duplicate word number",
        ),
    ],
)
def test_parse_tesseract_tsv_rejects_malformed_output_without_echoing_text(
    raw_tsv: bytes,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message) as error:
        parse_tesseract_tsv(raw_tsv, input_sha256=VALID_SHA256)

    assert "private@example.com" not in str(error.value)


def test_tesseract_adapter_returns_engine_metadata_and_uses_argument_list(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "input image.png"
    source.write_bytes(b"synthetic")
    commands: list[list[str]] = []

    def fake_run(command: list[str], *, timeout_seconds: float):
        commands.append(command)
        stdout = b"tesseract 5.3.4\n" if "--version" in command else VALID_TSV.encode()
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr("privacylens.tesseract_ocr.shutil.which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr("privacylens.tesseract_ocr._run", fake_run)

    extraction = TesseractOCR(language="eng+ara").extract(
        source,
        input_sha256=VALID_SHA256,
    )

    assert extraction.engine == "tesseract"
    assert extraction.engine_version == "5.3.4"
    assert extraction.languages == ("eng", "ara")
    assert commands[1] == [
        "/usr/bin/tesseract",
        str(source.resolve()),
        "stdout",
        "-l",
        "eng+ara",
        "tsv",
    ]


def test_tesseract_failure_does_not_echo_stderr_pii(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "input.png"
    source.write_bytes(b"synthetic")

    def fake_run(command: list[str], *, timeout_seconds: float):
        if "--version" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=b"tesseract 5.3.4\n",
                stderr=b"",
            )
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=b"private.person@example.com",
        )

    monkeypatch.setattr("privacylens.tesseract_ocr.shutil.which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr("privacylens.tesseract_ocr._run", fake_run)

    with pytest.raises(ValueError, match="exit code 1") as error:
        TesseractOCR().extract(source, input_sha256=VALID_SHA256)

    assert "private.person@example.com" not in str(error.value)


def test_tesseract_adapter_reports_missing_executable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("privacylens.tesseract_ocr.shutil.which", lambda _: None)

    with pytest.raises(FileNotFoundError, match="install Tesseract OCR"):
        TesseractOCR().extract(tmp_path / "input.png", input_sha256=VALID_SHA256)


@pytest.mark.parametrize("language", ["eng;rm", "../eng", "ENG", "e", "eng+"])
def test_tesseract_language_rejects_command_or_path_injection(language: str) -> None:
    with pytest.raises(ValueError, match="trained-data identifiers"):
        TesseractOCR(language=language)


def test_tesseract_timeout_is_sanitized(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=2, stderr=b"private@example.com")

    monkeypatch.setattr("privacylens.tesseract_ocr.subprocess.run", timeout)

    with pytest.raises(ValueError, match="2-second timeout") as error:
        _run(["tesseract", "input.png"], timeout_seconds=2)

    assert "private@example.com" not in str(error.value)
