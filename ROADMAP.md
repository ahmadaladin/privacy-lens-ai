# PrivacyLens roadmap

## v0.1 — Image redaction foundation

- [x] Project structure and continuous integration
- [x] Detector interface
- [x] Face-detection baseline
- [x] Blur, pixelation, and solid masking
- [x] Command-line interface
- [x] JSON audit manifest
- [x] Explicit image validation and source-overwrite protection
- [x] EXIF metadata removal verification
- [x] Fault-isolated batch processing with metadata-only failed-file quarantine

## v0.2 — OCR and review

- [ ] OCR text-region detection
- [x] Email and phone-number recognizers
- [x] Plain-text redaction pipeline with value-free span manifest
- [x] Confidence thresholds and versioned configurable policies
- [ ] Visual review interface
- [ ] Manual bounding-box correction

## v0.3 — Multilingual documents

- [ ] Arabic and English OCR evaluation
- [ ] Custom Arabic and regional PII recognizers
- [ ] Multi-page PDF processing
- [ ] Document-level audit reports

## v0.4 — AI dataset workflow

- [ ] Recursive batch processing
- [ ] YOLO and COCO annotation preservation
- [ ] Recursive quarantine with resume and retry controls
- [ ] Dataset-level risk summary
- [ ] CI privacy gate

## v0.5 — Video

- [ ] Frame extraction and reconstruction
- [ ] Face and plate tracking
- [ ] Temporally consistent redaction
- [ ] Video audit report

## v1.0 — Evaluated release

- [ ] Synthetic multilingual benchmark
- [ ] Precision, recall, failure, and latency reporting
- [ ] Docker image
- [ ] Stable Python API and CLI
- [ ] Complete security and limitation documentation
- [ ] Demonstration video and tagged release

## Planning rule

Each daily task must have testable acceptance criteria. A task is complete only when its relevant tests pass and its limitation is documented. Large features are divided into smaller issues rather than forced into one commit.
