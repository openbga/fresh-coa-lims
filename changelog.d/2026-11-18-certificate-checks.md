---
date: 2026-11-18
type: added
impact: high
title: Check whether a certificate someone holds was issued here and is still current
area: Certificates
link: reporting:check
pr: 57
---
**Check a certificate** on the certificate list compares a certificate file, or its SHA-256, with every version issued and answers whether it is genuine and current, replaced by a later version, or withdrawn. The file is never kept. A laboratory can also let its customers make the same check without an account, at an address it gives them. Each check that found a certificate is listed under **Checks** on its page, which warns when a recipient still checks a withdrawn certificate.

## Technical notes

- Migration `reporting.0006_certificate_checks`: append-only `CertificateCheck` (its insert trigger refuses an answer the certificate does not give), the one-row `CheckWindow`, and indexes on `ReportVersion.pdf_sha256` and `data_sha256`.
- New page `reports/check/` (URL name `reporting:check`, every reading role, in the form dialog) and, only with `CERTIFICATE_CHECK=true`, `check/` (URL name `certificate_check`) without an account, linked from the sign-in page. Off by default; it starts no session and sends `Cache-Control: no-store` and `X-Robots-Tag: noindex`.
- `CERTIFICATE_CHECK_RATE` (default 20, 1 to 600) bounds checks without an account per minute for the whole deployment, before the request body is read; past it the page answers 429 with `Retry-After`. Keep per-address rate limiting at the reverse proxy.
- Uploads are hashed as they arrive and never stored, within `RAW_DATA_MAX_BYTES`. Checks without an account are kept once a day for each version and answer, and a cross-site POST is refused with 403 before it is counted. The lot record export adds the section `report_checks`. The certificate prints nothing new.
