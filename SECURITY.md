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
- Batch quarantine stores failure metadata only; it never copies or moves the sensitive input.
- Treat filenames and local audit manifests as potentially sensitive operational data.

Rule-based email and phone recognition can miss PII or classify ordinary text
as PII. Phone recognition does not validate whether a number is assigned or
valid for a country. Review sanitized output before it leaves the trusted
environment.

PrivacyLens does not claim that its output is automatically compliant with GDPR, HIPAA, or any other regulation.
