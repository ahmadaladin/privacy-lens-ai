# Security policy

## Supported versions

PrivacyLens is pre-release software. Security fixes are applied to the latest version only.

## Reporting

Do not open a public issue containing personal information, private files, or unredacted screenshots. Report a vulnerability without attaching sensitive source data.

## Safe use

- Treat every automatic detection result as potentially incomplete.
- Review outputs before publishing or sharing them.
- Never use real identity documents as public test fixtures.
- Keep original files outside the repository.
- Do not log OCR text or other detected PII.
- Text audit manifests store categories and character spans, never matched values.
- Text processing refuses source overwrite, requires UTF-8 `.txt` files, and limits inputs to 5 MiB.
- Policy files are versioned, size-limited, and reject unknown keys and PII categories.
- Unscored findings are redacted by default; `unscored_action: retain` must be an explicit choice.
- Manual review plans are versioned, size-limited, and bound to the source SHA-256.
- Invalid, duplicate, or out-of-bounds manual regions stop processing before output is written.
- CLI manual-review runs require a manifest so each human decision leaves an audit record.
- OCR sidecars contain raw extracted text and must be protected like source images.
- OCR sidecars are versioned, size-limited, and bound to the source SHA-256.
- Invalid or out-of-bounds OCR observations stop processing before output is written.
- OCR-sidecar audit manifests store only counts, categories, and boxes, never extracted text.
- CLI OCR-sidecar runs require a manifest so sidecar-driven redaction leaves an audit record.
- Batch quarantine stores failure metadata only; it never copies or moves the sensitive input.
- Treat filenames and local audit manifests as potentially sensitive operational data.

Rule-based email and phone recognition can miss PII or classify ordinary text
as PII. Phone recognition does not validate whether a number is assigned or
valid for a country. Review sanitized output before it leaves the trusted
environment.

A policy can deliberately retain findings by category, threshold, or unscored
behavior. Treat any output with a non-zero `retained_count` as review output,
not sanitized output. The manifest records actions and reasons without storing
the matched values. The CLI returns exit code `1` and sets `review_required`
when any finding is retained.

Image fingerprints allow audit correlation and should be treated as sensitive
operational metadata. A valid manual plan deliberately replaces automatic
detections, including when its region list is empty. Only trusted reviewers
should create or approve review plans.

OCR confidence describes extraction quality, not the probability that extracted
text is PII. PrivacyLens therefore validates but does not reuse the sidecar
score as a PII confidence. Current rule-based PII findings remain unscored.
When character-level coordinates are unavailable, PrivacyLens redacts the whole
OCR observation box. This can remove extra non-sensitive pixels but avoids
leaving a partial sensitive value visible.

PrivacyLens does not claim that its output is automatically compliant with GDPR, HIPAA, or any other regulation.
