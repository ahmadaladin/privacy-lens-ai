import json
from pathlib import Path

import pytest

from privacylens import cli
from privacylens.text_pipeline import MAX_TEXT_BYTES, process_text_file


def test_text_pipeline_redacts_pii_and_writes_value_free_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    output = tmp_path / "sanitized.txt"
    manifest = tmp_path / "audit.json"
    email = "demo.person+qa@example.com"
    phone = "+60 12-345 6789"
    original = f"Contact {email} or {phone}."
    source.write_text(original, encoding="utf-8")

    result = process_text_file(source, output)
    result.write_manifest(manifest)

    assert source.read_text(encoding="utf-8") == original
    assert output.read_text(encoding="utf-8") == "Contact [EMAIL] or [PHONE]."
    manifest_text = manifest.read_text(encoding="utf-8")
    manifest_data = json.loads(manifest_text)
    assert email not in manifest_text
    assert phone not in manifest_text
    assert str(tmp_path) not in manifest_text
    assert manifest_data["input_name"] == "notes.txt"
    assert manifest_data["output_name"] == "sanitized.txt"
    assert [item["kind"] for item in manifest_data["detections"]] == [
        "email",
        "phone",
    ]
    assert all(item["score"] is None for item in manifest_data["detections"])


def test_text_pipeline_refuses_to_overwrite_source(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("Synthetic only", encoding="utf-8")

    with pytest.raises(ValueError, match="must be different"):
        process_text_file(source, source)


def test_text_pipeline_rejects_invalid_utf8(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"\xff\xfe")

    with pytest.raises(ValueError, match="not valid UTF-8"):
        process_text_file(source, tmp_path / "sanitized.txt")


def test_text_pipeline_enforces_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_bytes(b"x" * (MAX_TEXT_BYTES + 1))

    with pytest.raises(ValueError, match="safety limit"):
        process_text_file(source, tmp_path / "sanitized.txt")


def test_text_cli_writes_output_and_manifest(tmp_path: Path, capsys) -> None:
    source = tmp_path / "notes.txt"
    output = tmp_path / "sanitized.txt"
    manifest = tmp_path / "audit.json"
    source.write_text("Email fake@example.com", encoding="utf-8")

    exit_code = cli.main(
        [
            str(source),
            str(output),
            "--text",
            "--manifest",
            str(manifest),
        ]
    )

    assert exit_code == 0
    assert output.read_text(encoding="utf-8") == "Email [EMAIL]"
    assert manifest.is_file()
    assert "Redacted 1 text finding(s)" in capsys.readouterr().out
