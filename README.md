# PrivacyLens

[![quality](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml/badge.svg)](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml)

PrivacyLens is a local-first privacy pipeline for detecting and redacting personally identifiable information (PII) from AI datasets.

The project is being developed in small, tested releases. The current release
supports face redaction in images and rule-based email and phone redaction in
plain text. It can also ingest fingerprint-bound observations from an OCR
engine and map recognized PII back to image regions. Future releases will add
evaluated OCR adapters, Arabic and English evaluation, PDFs, dataset-level
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
- Map provider-neutral OCR observations containing PII back to image regions
- Bind OCR observations to the exact source image with SHA-256
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

Correct automatic boxes with a fingerprint-bound manual review plan:

```json
{
  "schema_version": "1.0",
  "input_sha256": "<copy input_sha256 from audit.json>",
  "regions": [
    {"kind": "face", "box": [42, 18, 126, 117]}
  ]
}
```

```bash
privacy-lens input.jpg reviewed.jpg --review-plan review.json --style solid --manifest reviewed-audit.json
```

The review plan replaces automatic detections with exactly the approved
regions. Its SHA-256 binding prevents coordinates prepared for one image from
being applied to another. Invalid, duplicate, or out-of-bounds regions stop
processing before an output is written. An empty `regions` list is an explicit
human approval that the image contains no regions to redact. CLI review runs
require `--manifest` so the manual decision always leaves an audit record.

Redact image regions described by an upstream OCR engine:

```json
{
  "schema_version": "1.0",
  "input_sha256": "<SHA-256 of the exact encoded input image>",
  "observations": [
    {
      "text": "Contact fake.person@example.com",
      "box": [18, 42, 246, 76],
      "score": 0.94
    }
  ]
}
```

```bash
privacy-lens input.png sanitized.png --ocr-sidecar ocr.json --style solid --manifest audit.json
```

The sidecar is an engine-neutral integration contract, not an OCR
implementation. Tesseract, EasyOCR, a document model, or another extractor can
produce the same shape. PrivacyLens verifies that the sidecar fingerprint
matches the exact input, validates every observation before writing output,
passes each observation's text through the existing PII recognizers, and
redacts the whole observation box when supported PII is found.

> [!WARNING]
> OCR sidecars contain raw extracted text and may contain PII. Keep them inside
> the same protected boundary as source files; do not commit, publish, or log
> them. Audit manifests record only the sidecar schema, observation count, PII
> categories, and boxes—not OCR text.

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

image + OCR sidecar -> fingerprint/bounds validation -> text PII recognizers
                                                         |
                                                         v
                                      value-free boxes -> image redaction
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
| Fingerprint-bound review plan | Manual corrections cannot silently be applied to a different source image. |
| Stable review contract | A future visual interface can emit the same validated JSON used by the CLI and Python API. |
| Provider-neutral OCR sidecar | OCR engines can change without coupling extraction, PII recognition, image redaction, or audit logic. |
| Fingerprint-bound OCR observations | Stale text coordinates cannot silently redact the wrong image. |
| Separate confidence semantics | OCR extraction scores are not reused as PII confidence; rule-based PII findings remain `null`. |
| Coarse observation-box redaction | The whole OCR box is masked because character-level geometry is unavailable; this favors privacy over visual precision. |

## Example manifest

```json
{
  "schema_version": "1.2",
  "input_path": "input.jpg",
  "output_path": "output.jpg",
  "input_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "style": "blur",
  "detector": "HaarFaceDetector",
  "human_reviewed": false,
  "review_plan_schema_version": null,
  "ocr_sidecar_schema_version": null,
  "ocr_sidecar_observation_count": null,
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
negatives, so outputs still require review. PrivacyLens does not yet run an OCR
engine itself. Sidecar quality, reading order, coordinate accuracy, and missed
text remain the upstream extractor's responsibility and require benchmark
evaluation.

## License

Released under the [MIT License](LICENSE).
