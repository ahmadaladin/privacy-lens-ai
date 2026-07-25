"""PrivacyLens command-line interface."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from privacylens.batch import process_directory
from privacylens.pipeline import process_image
from privacylens.redaction import REDACTION_STYLES
from privacylens.text_pipeline import process_text_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="privacy-lens",
        description="Detect and redact sensitive image or text regions locally.",
    )
    parser.add_argument("input", help="path to an image, text file, or batch directory")
    parser.add_argument("output", help="path for the sanitized output")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--batch",
        action="store_true",
        help="process supported images directly inside an input directory",
    )
    mode.add_argument(
        "--text",
        action="store_true",
        help="detect and redact email and phone spans in a UTF-8 text file",
    )
    parser.add_argument(
        "--style",
        choices=sorted(REDACTION_STYLES),
        default="blur",
        help="image redaction transformation; ignored in text mode (default: blur)",
    )
    parser.add_argument("--manifest", help="optional JSON audit-manifest path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.batch:
            batch_result = process_directory(args.input, args.output, style=args.style)
        elif args.text:
            text_result = process_text_file(args.input, args.output)
        else:
            result = process_image(args.input, args.output, style=args.style)
    except (FileNotFoundError, ValueError) as error:
        print(f"privacy-lens: error: {error}", file=sys.stderr)
        return 2

    if args.batch:
        if args.manifest:
            batch_result.write_manifest(args.manifest)
        print(
            f"Processed {batch_result.processed_count} image(s); "
            f"{batch_result.failed_count} failed: {args.output}"
        )
        return 1 if batch_result.failed_count else 0

    if args.text:
        if args.manifest:
            text_result.write_manifest(args.manifest)
        print(f"Redacted {len(text_result.detections)} text finding(s): {args.output}")
        return 0

    if args.manifest:
        result.write_manifest(args.manifest)
    print(f"Redacted {len(result.detections)} face(s): {result.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
