import json
from pathlib import Path

import pytest

from privacylens import cli
from privacylens.policy import RedactionPolicy
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
    assert manifest_data["redacted_count"] == 2
    assert manifest_data["retained_count"] == 0
    assert manifest_data["review_required"] is False
    assert manifest_data["policy"]["unscored_action"] == "redact"
    assert all(item["action"] == "redact" for item in manifest_data["detections"])
    assert all(item["reason"] == "unscored_fail_closed" for item in manifest_data["detections"])


def test_text_policy_can_retain_unselected_kind_with_auditable_reason(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    output = tmp_path / "review.txt"
    manifest = tmp_path / "audit.json"
    phone = "+60 12-345 6789"
    source.write_text(f"Email fake@example.com or phone {phone}.", encoding="utf-8")
    policy = RedactionPolicy(redact_kinds=frozenset({"email"}))

    result = process_text_file(source, output, policy=policy)
    result.write_manifest(manifest)

    assert output.read_text(encoding="utf-8") == f"Email [EMAIL] or phone {phone}."
    manifest_text = manifest.read_text(encoding="utf-8")
    manifest_data = json.loads(manifest_text)
    assert phone not in manifest_text
    assert manifest_data["redacted_count"] == 1
    assert manifest_data["retained_count"] == 1
    assert manifest_data["review_required"] is True
    assert [item["action"] for item in manifest_data["detections"]] == [
        "redact",
        "retain",
    ]
    assert manifest_data["detections"][1]["reason"] == "kind_not_selected"


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


def test_text_cli_loads_policy_and_reports_retained_findings(
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "notes.txt"
    output = tmp_path / "review.txt"
    policy_path = tmp_path / "policy.json"
    source.write_text(
        "Email fake@example.com or +60 12-345 6789.",
        encoding="utf-8",
    )
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "redact_kinds": ["email"],
                "unscored_action": "redact",
            }
        ),
        encoding="utf-8",
    )

    exit_code = cli.main(
        [
            str(source),
            str(output),
            "--text",
            "--policy",
            str(policy_path),
        ]
    )

    assert exit_code == 1
    assert "retained 1 by policy" in capsys.readouterr().out
    assert output.read_text(encoding="utf-8") == ("Email [EMAIL] or +60 12-345 6789.")
