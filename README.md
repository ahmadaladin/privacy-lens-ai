# PrivacyLens

[![quality](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml/badge.svg)](https://github.com/ahmadaladin/privacy-lens-ai/actions/workflows/tests.yml)

PrivacyLens is a local-first privacy pipeline for detecting and redacting personally identifiable information (PII) from AI datasets.

The project is being developed in small, tested releases. The first release supports face detection and image redaction from the command line. Future releases will add OCR-based PII detection, Arabic and English recognizers, PDFs, dataset-level processing, annotation preservation, evaluation, and video.

> [!IMPORTANT]
> Automated redaction can miss sensitive information. PrivacyLens is an engineering tool with a human-review roadmap, not a guarantee of regulatory compliance.

## Current capabilities

- Detect frontal faces locally with an OpenCV baseline detector
- Redact detected regions using blur, pixelation, or a solid mask
- Process JPG, JPEG, and PNG images
- Write a JSON audit manifest containing detection coordinates
- Process an image directory without one corrupt file aborting the full batch
- Quarantine failed-file metadata without copying sensitive source files
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

### Engineering decisions

| Decision | Why it matters |
| --- | --- |
| Local-first processing | Sensitive files do not need to leave the operator's machine. |
| Detector protocol | Vision and OCR models can be replaced without coupling them to file I/O. |
| Structured audit manifest | Every output can be traced to the detector, policy, and regions used. |
| Honest confidence semantics | The Haar baseline reports `null`, not a fabricated probability. |
| Source-overwrite protection | A failed command cannot silently destroy the original evidence. |
| Metadata-only quarantine | Failed inputs remain untouched and are not duplicated into a less-controlled output folder. |

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

PrivacyLens is under active development. The current face detector is an intentionally lightweight baseline; its accuracy and limitations will be benchmarked before a stable release.

## License

Released under the [MIT License](LICENSE).
