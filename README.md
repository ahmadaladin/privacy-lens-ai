# PrivacyLens

[![quality](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml/badge.svg)](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml)

PrivacyLens is a local-first privacy pipeline for detecting and redacting personally identifiable information (PII) from AI datasets.

The project is being developed in small, tested releases. The current release
supports face redaction in images and rule-based email and phone redaction in
plain text. Future releases will connect OCR output to the same text
recognizers, then add Arabic and English evaluation, PDFs, dataset-level
processing, annotation preservation, and video.

> [!IMPORTANT]
> Automated redaction can miss sensitive information. PrivacyLens is an engineering tool with a human-review roadmap, not a guarantee of regulatory compliance.

## Current capabilities

- Detect frontal faces locally with an OpenCV baseline detector
- Redact detected regions using blur, pixelation, or a solid mask
- Process JPG, JPEG, and PNG images
- Write a JSON audit manifest containing detection coordinates
- Process an image directory without one corrupt file aborting the full batch
- Quarantine failed-file metadata without copying sensitive source files
- Detect email addresses and plausible phone numbers in local UTF-8 text files
- Replace text findings with category markers and write value-free span manifests
- Remove embedded image metadata during re-encoding
- Refuse to overwrite the original sensitive input
- Run without sending files to an external service
- Test and lint the core pipeline automatically on Python 3.11 and 3.12

## Quick start

PrivacyLens requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Redact faces in an image:

```bash
privacy-lens input.jpg output.jpg --style blur --manifest audit.json
```

Process all supported images directly inside a directory:

```bash
privacy-lens input-directory output-directory --batch --style solid
```

Batch outputs are separated into:

- `sanitized/` for successfully redacted images
- `manifests/` for per-image audit records
- `quarantine/` for metadata-only failure records
- `batch-manifest.json` for deterministic processed/failed totals

Batch mode intentionally does not recurse into subdirectories yet. It returns
exit code `1` when any candidate fails, while preserving successful outputs so
operators and CI jobs can detect partial failure.

Redact supported PII patterns in a UTF-8 text file:

```bash
privacy-lens notes.txt sanitized.txt --text --manifest text-audit.json
```

Text manifests record categories and character spans, but never the matched
email address or phone number. The source file is left unchanged.

Apply a versioned policy:

```json
{
  "schema_version": "1.0",
  "redact_kinds": ["email"],
  "minimum_score": 0.8,
  "unscored_action": "redact"
}
```

```bash
privacy-lens notes.txt review.txt --text --policy policy.json --manifest audit.json
```

Policies are strict: unknown keys, unknown PII categories, unsupported schema
versions, and invalid thresholds stop processing. `unscored_action` defaults
to `redact`, which fails closed for deterministic rules that do not produce a
calibrated confidence. A policy can explicitly retain findings; such output is
for controlled review and must not be assumed sanitized. The command returns
exit code `1` whenever a finding is retained, and the manifest sets
`review_required` to `true`, so automated workflows cannot mistake review
output for a fully redacted result.

Run the tests:

```bash
pytest
```

## How it works

```text
                        +-----------------+
image -> validation -> | local detector  | -> detections
                        +-----------------+        |
                                                 v
                         audit manifest <- redaction policy -> sanitized image
```

The detector and redaction engine are separate. This allows stronger face,
license-plate, and OCR detectors to be added without rewriting the pipeline.
Batch orchestration adds failure isolation around the same single-image
pipeline rather than maintaining a second redaction implementation.
The text pipeline separates recognition from file processing and replacement.
Future OCR can supply extracted text to these recognizers without embedding
privacy rules inside an OCR engine.

### Engineering decisions

| Decision | Why it matters |
| --- | --- |
| Local-first processing | Sensitive files do not need to leave the operator's machine. |
| Detector protocol | Vision and OCR models can be replaced without coupling them to file I/O. |
| Structured audit manifest | Every output can be traced to the detector, policy, and regions used. |
| Honest confidence semantics | The Haar baseline reports `null`, not a fabricated probability. |
| Source-overwrite protection | A failed command cannot silently destroy the original evidence. |
| Metadata-only quarantine | Failed inputs remain untouched and are not duplicated into a less-controlled output folder. |
| Value-free text manifest | Auditing can identify what rule fired and where without duplicating matched PII. |
| Uncalibrated rule scores are `null` | Regex matches are decisions, not statistically calibrated probabilities. |
| Versioned policy-as-code | Category, threshold, and unscored decisions are reproducible and reject silent configuration typos. |
| Fail-closed unscored default | Findings without calibrated scores are redacted unless a policy explicitly retains them. |

## Example manifest

```json
{
  "schema_version": "1.0",
  "input_path": "input.jpg",
  "output_path": "output.jpg",
  "style": "blur",
  "detector": "HaarFaceDetector",
  "detections": [
    {
      "kind": "face",
      "score": null,
      "box": [42, 18, 126, 117]
    }
  ]
}
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the phased development plan and [LEARNING_LOG.md](LEARNING_LOG.md) for the concepts Ahmed will test and explain during development.

## Privacy and security

- Never commit real IDs or private personal files.
- Use synthetic or explicitly licensed samples in tests and demonstrations.
- Review uncertain detections before sharing sanitized data.
- See [SECURITY.md](SECURITY.md) for reporting and safe-use guidance.

## Project status

PrivacyLens is under active development. The face detector and text recognizers
are intentionally lightweight baselines that require evaluation before a
stable release. The current email rule targets conventional ASCII addresses;
the phone rule checks plausible digit counts and separators but does not
validate country numbering plans. Both can produce false positives and false
negatives, so outputs still require review.

## License

Released under the [MIT License](LICENSE).
