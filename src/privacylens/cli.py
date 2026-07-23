"""PrivacyLens command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from privacylens.pipeline import process_image
from privacylens.redaction import REDACTION_STYLES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="privacy-lens",
        description="Detect and redact faces from an image locally.",
    )
    parser.add_argument("input", help="path to a JPG or PNG image")
    parser.add_argument("output", help="path for the sanitized image")
    parser.add_argument(
        "--style",
        choices=sorted(REDACTION_STYLES),
        default="blur",
        help="redaction transformation (default: blur)",
    )
    parser.add_argument("--manifest", help="optional JSON audit-manifest path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = process_image(args.input, args.output, style=args.style)
    except (FileNotFoundError, ValueError) as error:
        print(f"privacy-lens: error: {error}", file=sys.stderr)
        return 2
    if args.manifest:
        result.write_manifest(args.manifest)
    print(f"Redacted {len(result.detections)} face(s): {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
