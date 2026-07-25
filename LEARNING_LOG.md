# Learning log

This file records the concepts Ahmed should be able to demonstrate and explain as PrivacyLens develops.

## Day 1 — Detection and redaction pipeline

### Concepts

- A detector locates a sensitive region and returns a bounding box.
- Redaction transforms pixels inside that box.
- Separating detection from redaction makes models and privacy policies replaceable.
- Automated tests verify technical behavior; user testing verifies usefulness.
- A detector must not invent confidence values when its output is not calibrated.
- Safe defaults prevent the sanitized output from overwriting the sensitive source.

### Files to inspect

- `src/privacylens/models.py`
- `src/privacylens/redaction.py`
- `src/privacylens/detectors/haar_face.py`
- `src/privacylens/pipeline.py`

### Practice

1. Run PrivacyLens on two safe images: one frontal face and one image without a face.
2. Compare `blur`, `pixelate`, and `solid` redaction styles.
3. Open the JSON manifest and identify the four bounding-box coordinates.
4. Explain why a lightweight Haar detector is only a baseline.
5. Explain why the manifest records a missing confidence as `null` instead of `1.0`.

### Interview explanation

> I separated the detection and redaction components so the system can replace its initial face detector without changing file processing, audit reporting, or redaction policies. I also tested pixel-level behavior independently from model accuracy.

## Day 2 — Fault-isolated dataset batches

### Concepts

- Batch processing should reuse the tested single-image pipeline instead of duplicating logic.
- One corrupt image should not discard successful outputs from other images.
- A partial batch failure must be machine-visible through a non-zero exit code.
- Quarantine can isolate failure metadata without copying sensitive source data.
- Deterministic file ordering makes manifests, tests, and incident investigation reproducible.
- Relative output paths reduce accidental disclosure of local usernames and directory layouts.

### Files to inspect

- `src/privacylens/batch.py`
- `src/privacylens/cli.py`
- `tests/test_batch.py`
- `tests/test_cli.py`

### Practice

1. Create a folder containing two safe test images and one corrupt `.jpg`.
2. Run `privacy-lens input-directory output-directory --batch --style solid`.
3. Confirm the valid images are sanitized even though the command returns exit code `1`.
4. Inspect `batch-manifest.json` and the metadata-only `quarantine/` record.
5. Explain why the failed source file is not copied into the quarantine directory.

### Interview explanation

> I added fault-isolated batch orchestration around the existing image pipeline. Successful files remain usable when another file is corrupt, while the command reports partial failure to CI and creates a metadata-only quarantine record without duplicating sensitive input.

## Day 3 — Privacy-safe text PII redaction

### Concepts

- Recognition identifies the category and character span; redaction replaces the span.
- A text recognizer protocol keeps privacy rules independent from file I/O and future OCR engines.
- Audit records can retain a category and span without copying the sensitive value.
- Recognizer priority resolves overlap, such as a numeric email username that resembles a phone number.
- A rule match is not a calibrated probability, so its score is recorded as `null`.
- Unicode-aware digit handling supports more scripts, but a plausible phone pattern is not country-level validation.

### Files to inspect

- `src/privacylens/text_recognition.py`
- `src/privacylens/text_pipeline.py`
- `tests/test_text_recognition.py`
- `tests/test_text_pipeline.py`

### Practice

1. Create a UTF-8 `.txt` file containing synthetic email and phone values.
2. Run `privacy-lens notes.txt sanitized.txt --text --manifest audit.json`.
3. Confirm the source remains unchanged and the output contains `[EMAIL]` and `[PHONE]`.
4. Confirm the manifest contains spans but none of the matched values or absolute local path.
5. Try Arabic-Indic phone digits and a date, then explain the different outcomes.
6. Explain how OCR output can later enter the same recognizer without changing its rules.

### Interview explanation

> I built the PII layer independently from OCR so text extraction and privacy recognition can evolve separately. The pipeline replaces matched spans locally, resolves overlapping recognizers deterministically, and records only categories and offsets in its audit manifest. I deliberately report rule scores as null and document that pattern matching still needs benchmark evaluation and human review.
