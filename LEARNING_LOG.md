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
