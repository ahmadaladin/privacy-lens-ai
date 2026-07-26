from pathlib import Path

import cv2
import numpy as np

from privacylens import cli
from privacylens.models import BoundingBox, Detection


class FixedDetector:
    def detect(self, image: np.ndarray) -> list[Detection]:
        return [Detection("face", BoundingBox(1, 1, 4, 4), 0.9)]


def test_batch_cli_reports_partial_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    assert cv2.imwrite(
        str(input_dir / "valid.png"),
        np.full((6, 6, 3), 255, dtype=np.uint8),
    )
    (input_dir / "bad.jpg").write_bytes(b"broken")

    original_process_directory = cli.process_directory

    def process_with_fixed_detector(input_path, output_path, *, style):
        return original_process_directory(
            input_path,
            output_path,
            style=style,
            detector=FixedDetector(),
        )

    monkeypatch.setattr(cli, "process_directory", process_with_fixed_detector)

    exit_code = cli.main([str(input_dir), str(output_dir), "--batch"])

    assert exit_code == 1
    assert "Processed 1 image(s); 1 failed" in capsys.readouterr().out


def test_policy_option_is_rejected_outside_text_mode(tmp_path: Path, capsys) -> None:
    exit_code = cli.main(
        [
            str(tmp_path / "input.png"),
            str(tmp_path / "output.png"),
            "--policy",
            str(tmp_path / "policy.json"),
        ]
    )

    assert exit_code == 2
    assert "--policy requires --text" in capsys.readouterr().err
