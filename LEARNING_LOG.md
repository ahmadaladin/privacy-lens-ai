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

## Day 4 — Versioned redaction policy

### Concepts

- Detection answers what was found; policy decides what action to take.
- Policy-as-code makes category, confidence, and unscored behavior reproducible.
- Strict schema validation prevents a typo from silently disabling protection.
- A confidence threshold is meaningful only for a calibrated model score.
- Fail-closed handling redacts unscored findings unless retention is explicit.
- A retained finding remains sensitive even when its value is absent from the audit manifest.
- Review-required output returns a non-zero status so CI cannot mistake it for sanitized output.

### Files to inspect

- `src/privacylens/policy.py`
- `src/privacylens/text_pipeline.py`
- `tests/test_policy.py`
- `tests/test_text_pipeline.py`

### Practice

1. Run text redaction without a policy and confirm all unscored findings are redacted.
2. Create a policy that selects only `email` and run it on synthetic email and phone values.
3. Confirm the phone remains in review output, `retained_count` is `1`, and the command returns exit code `1`.
4. Confirm the manifest records `kind_not_selected` without storing the phone value.
5. Misspell `email` in the policy and verify processing stops instead of silently continuing.
6. Explain why `minimum_score` cannot turn the current regex match into a confidence score.

### Interview explanation

> I separated detection from policy decisions and added a strict, versioned policy-as-code layer. It supports category selection, calibrated-score thresholds, and explicit unscored behavior. The default fails closed, configuration typos stop processing, and every redact or retain decision is auditable without copying the matched PII into the manifest.

## Day 5 — Fingerprint-bound manual review

### Concepts

- Human-in-the-loop review needs a stable contract, not UI-specific business logic.
- A source fingerprint prevents corrected coordinates from being applied to the wrong image.
- Manual regions replace model detections so the reviewer’s decision is deterministic and auditable.
- Coordinate validation must reject negative, empty, duplicate, and out-of-bounds boxes.
- Validation must finish before writing an output to avoid producing misleading artifacts.
- An empty region list is an explicit human approval, not proof that the detector found nothing.

### Files to inspect

- `src/privacylens/review.py`
- `src/privacylens/pipeline.py`
- `tests/test_review.py`
- `tests/test_pipeline.py`

### Practice

1. Run automatic image redaction with `--manifest` and copy its `input_sha256`.
2. Create `review.json`, adjust one synthetic bounding box, and rerun with `--review-plan`.
3. Confirm only the reviewed region is redacted and `human_reviewed` is `true`.
4. Change one character of `input_sha256` and confirm no output is created.
5. Try a box extending past the image width and confirm validation stops processing.
6. Explain how a future visual review UI can generate the same review-plan JSON.

### Interview explanation

> I added a human-review contract that is independent of any UI framework. Reviewers can replace automatic detections with corrected regions, but the plan is cryptographically bound to the exact source image and strictly validated before output is written. That prevents stale coordinates, silent schema mistakes, and out-of-bounds corrections while giving a future web interface a stable backend contract.

## Day 6 — Provider-neutral OCR observation bridge

### Concepts

- OCR extracts text and coordinates; PII recognition decides whether that text is sensitive.
- An engine-neutral sidecar prevents Tesseract, EasyOCR, or a future document model from becoming coupled to redaction and audit logic.
- OCR output contains raw text and must be protected like the sensitive source.
- A source fingerprint prevents stale OCR coordinates from being applied to a different image.
- OCR confidence is not PII confidence; rule-based PII decisions remain unscored.
- Whole-observation redaction is a privacy-first fallback when character-level geometry is unavailable.
- Audit records can prove what category and box were redacted without copying OCR text.

### Files to inspect

- `src/privacylens/ocr.py`
- `src/privacylens/pipeline.py`
- `tests/test_ocr.py`
- `tests/test_pipeline.py`

### Practice

1. Use a synthetic image and calculate the SHA-256 of the exact encoded file.
2. Create an OCR sidecar with one fake email observation and one ordinary-text observation.
3. Run `privacy-lens input.png output.png --ocr-sidecar ocr.json --style solid --manifest audit.json`.
4. Confirm the email box is redacted, the ordinary-text box is unchanged, and the manifest contains no extracted text.
5. Change one fingerprint character and confirm processing stops without an output.
6. Explain why the OCR score is preserved only in the protected sidecar and the PII detection score is `null`.
7. Explain what an actual OCR adapter still needs to implement and evaluate.

### Interview explanation

> I added an engine-neutral boundary between OCR and privacy recognition. Upstream OCR provides fingerprint-bound text boxes, then the existing PII recognizers map sensitive observations back to image regions. The pipeline validates the full sidecar before writing, keeps raw OCR text out of audit records, and does not mislabel OCR confidence as PII confidence. This lets us evaluate or replace OCR engines without rewriting redaction and audit behavior.

## Day 7 — Local Tesseract OCR adapter

### Concepts

- An OCR adapter translates engine-specific output into the provider-neutral observation contract.
- Tesseract emits word-level TSV; grouping words by line allows spaced phone numbers to reach the existing recognizer intact.
- Subprocess arguments should be passed as a list without a shell, and user-controlled language identifiers need strict validation.
- Raw OCR output and stderr can contain sensitive text, so they must not be logged or copied into errors and manifests.
- Timeouts and output limits prevent an OCR subprocess from consuming unbounded application resources.
- OCR engine version and languages are reproducibility metadata; they do not prove model accuracy.
- A tested integration pipeline and an evaluated OCR model are different claims.

### Files to inspect

- `src/privacylens/tesseract_ocr.py`
- `src/privacylens/ocr.py`
- `src/privacylens/pipeline.py`
- `tests/test_tesseract_ocr.py`

### Practice

1. Confirm Tesseract and the English trained data are installed with `tesseract --version`.
2. Create a synthetic image containing a fake email and a spaced fake phone number.
3. Run `privacy-lens input.png output.png --ocr-engine tesseract --ocr-language eng --style solid --manifest audit.json`.
4. Confirm the PII line regions are redacted and the manifest records Tesseract's version and `eng`.
5. Search the manifest for the fake values and confirm neither appears.
6. Try `--ocr-language 'eng;anything'` and explain why it is rejected before execution.
7. Explain why passing tests does not replace an Arabic and English OCR benchmark.

### Interview explanation

> I implemented a local Tesseract adapter behind an engine-neutral OCR contract. It reconstructs word-level TSV into line observations, reuses the existing PII recognizers, and maps sensitive lines back to redaction boxes. The subprocess boundary uses strict arguments, timeouts, bounded output, and sanitized failures. Audit records capture the engine version and languages but never raw OCR text. I clearly separate integration correctness from OCR accuracy, which still needs multilingual benchmark evaluation.

## Day 8 — Fault-isolated OCR dataset batches

### Concepts

- Dataset orchestration should reuse the tested single-image OCR pipeline rather than duplicate extraction or redaction logic.
- A corrupt image or OCR failure should not discard successful sanitized outputs.
- Per-image manifests preserve engine version, languages, and redacted boxes without storing OCR text.
- The batch manifest records the processing mode and processor so runs remain operationally traceable.
- A partial failure returns a non-zero status so CI cannot treat an incomplete dataset as fully processed.
- Sequential execution gives deterministic ordering and predictable OCR resource use.
- Recursion, parallelism, resume, retry, and accuracy evaluation are separate capabilities that remain unfinished.

### Files to inspect

- `src/privacylens/batch.py`
- `src/privacylens/cli.py`
- `tests/test_batch.py`
- `tests/test_cli.py`

### Practice

1. Create a folder containing two safe synthetic text images and one corrupt `.jpg`.
2. Run `privacy-lens input output --batch --ocr-engine tesseract --ocr-language eng --style solid`.
3. Confirm both valid files have sanitized outputs and per-image manifests.
4. Confirm the corrupt file creates only a metadata record under `quarantine/`.
5. Inspect `batch-manifest.json` for `processing_mode`, `processor`, processed count, and failed count.
6. Confirm the command returns exit code `1` because the dataset is only partially complete.
7. Explain why sequential processing is a deliberate first release rather than an accidental limitation.

### Interview explanation

> I extended local OCR from one image to a fault-isolated dataset workflow without creating a second implementation. Batch orchestration reuses the same extraction, PII recognition, redaction, and value-free audit path for every file. Successful outputs survive individual OCR failures, quarantine contains metadata rather than sensitive copies, and partial completion is visible to CI. Execution is deterministic and sequential until bounded parallelism and resume semantics are designed.

## Day 9 — Privacy-safe dataset risk summary

### Concepts

- Operational observability answers what ran, failed, and was detected; evaluation answers how accurate the model is.
- Aggregate counts can support monitoring without exposing filenames, paths, hashes, coordinates, or matched PII.
- Completion states should distinguish empty, complete, partial, and fully failed batches.
- Summary invariants prevent contradictory totals from becoming trusted audit data.
- Images without automatic findings are not proven safe because the detector may have false negatives.
- Category counts show the dataset's detected privacy profile without centralizing sensitive examples.
- Precision and recall require labeled ground truth and cannot be inferred from production detection counts.

### Files to inspect

- `src/privacylens/risk_summary.py`
- `src/privacylens/batch.py`
- `tests/test_risk_summary.py`
- `tests/test_batch.py`

### Practice

1. Run an OCR batch containing one image with a fake email, one image with ordinary text, and one corrupt image.
2. Open `dataset-risk-summary.json` and identify the partial completion state.
3. Verify one image has findings, one has none, and one failed.
4. Confirm the summary contains no filenames, local paths, hashes, coordinates, or fake email value.
5. Remove all candidate images, rerun, and confirm the state becomes `empty` with `processing_attention_required: true`.
6. Explain why `images_without_findings` cannot be renamed to `safe_images`.
7. Explain what labeled data is needed before reporting precision and recall.

### Interview explanation

> I added a value-free observability layer for dataset processing. It aggregates completion, failure, OCR observation, and PII category counts while excluding source identifiers and matched values. The model enforces internally consistent totals and distinguishes empty, complete, partial, and failed runs. I explicitly label these as operational counts—not accuracy or safety metrics—because false negatives require a labeled benchmark and human review.

## Day 10 — Batch completeness and evidence-integrity CI gate

### Concepts

- A CI gate should distinguish an incomplete run from malformed or contradictory evidence.
- Exit codes are a machine-readable contract: `0` passes, `1` needs processing attention, and `2` means evidence is invalid.
- Generated manifests are untrusted inputs when a later CI job reads them.
- Strict schemas, bounded reads, duplicate-key rejection, and fixed relative paths reduce parser and path-traversal risks.
- Cross-checking independent batch and risk-summary totals catches accidental or deliberate tampering.
- Exact managed-directory inventories prevent stale outputs from an earlier run entering a later dataset.
- Artifact existence can be verified without opening potentially sensitive image contents.
- Processing completeness is not model accuracy, privacy assurance, or regulatory compliance.

### Files to inspect

- `src/privacylens/gate.py`
- `src/privacylens/risk_summary.py`
- `tests/test_gate.py`
- `tests/test_risk_summary.py`

### Practice

1. Run a complete batch and confirm `privacy-lens-gate output-directory` returns `0`.
2. Add a corrupt input, rerun into a fresh output directory, and confirm the gate returns `1`.
3. Change a count in `dataset-risk-summary.json` and confirm the gate returns `2`.
4. Replace an output path in `batch-manifest.json` with `../escape.png` and confirm it is rejected.
5. Confirm the gate output reports aggregate counts without filenames or source paths.
6. Explain why a valid partial batch is different from an invalid manifest.
7. Explain why a passing gate cannot replace the multilingual benchmark or human review.

### Interview explanation

> I added a CI-safe verification boundary around batch outputs. It treats generated JSON as untrusted, validates strict size-bounded schemas, rejects duplicate keys and path traversal, cross-checks the batch manifest against the value-free risk summary and quarantine records, and confirms expected artifacts exist without opening images. Separate exit codes distinguish a trustworthy but incomplete run from evidence that is malformed or contradictory. A pass means the pipeline completed consistently—not that the detector has perfect recall or that the dataset is compliant.

## Day 11 — Synthetic text PII benchmark and quality thresholds

### Concepts

- Precision measures how many predicted findings were correct; recall measures how many labeled findings were found.
- Exact-span matching requires the category, start offset, and end offset to agree with ground truth.
- F1 is the harmonic mean of precision and recall and cannot replace inspecting both.
- A negative example is needed to expose false positives; positive examples expose false negatives.
- CI thresholds turn evaluation into an explicit release contract rather than a dashboard-only number.
- Aggregate reports can retain metrics without duplicating benchmark text or labeled spans.
- A declared-synthetic dataset is a trust assertion, not something software can prove automatically.
- A small regression fixture detects known breakage but does not establish real-world generalization.
- Text-recognizer evaluation starts after text exists and therefore says nothing about OCR accuracy.

### Files to inspect

- `benchmarks/synthetic_text_v1.json`
- `src/privacylens/benchmark.py`
- `tests/test_benchmark.py`
- `.github/workflows/tests.yml`

### Practice

1. Run the committed benchmark with precision and recall thresholds of `1.0`.
2. Inspect the aggregate report and identify TP, FP, FN, precision, recall, and F1.
3. Change one expected phone span by one character and confirm the benchmark returns exit `1`.
4. Add an unexpected JSON field and confirm the benchmark returns exit `2`.
5. Confirm the report contains neither the synthetic email nor Arabic-digit phone value.
6. Explain why an exact-span mismatch creates one false positive and one false negative.
7. Explain why eight passing cases do not demonstrate Arabic OCR quality or production readiness.

### Interview explanation

> I added a versioned evaluation boundary for the rule-based text PII layer. It loads strictly validated, declared-synthetic English and Arabic-digit labels, uses exact category-and-span matching, and produces aggregate-only precision, recall, and F1 reports. Explicit thresholds block CI regressions, while separate exit codes distinguish a metric failure from an invalid benchmark. I deliberately scope the result to known text-recognition cases: it does not measure OCR, unseen data, fairness, or end-to-end privacy.
