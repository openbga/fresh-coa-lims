---
date: 2026-11-18
type: added
impact: medium
title: Certificates carry their data in a machine-readable form, inside a tagged PDF/A-3a file
area: Certificates
link: reporting:list
pr: 56
---
Each certificate issued or amended now holds its content as a JSON file, attached to the PDF and downloadable beside it with **Download data** on the version and certificate pages, where its checksum is shown. The PDF is written for long-term keeping and for assistive technology (tagged PDF/A-3a, also declaring PDF/UA-1). A certificate for one customer or market carries that scope only, and certificates issued before stay exactly as issued, without data.

## Technical notes

- Migration `reporting.0005_certificate_data`: `ReportVersion.data` (the JSON bytes, null for versions issued before), `data_sha256` and `pdf_format` (`PDF/A-3a, PDF/UA-1`), guarded like every issued column, with the check constraint `reportversion_data`.
- Schema `oq.certificate-data/1`, described in `docs/certificate-data.md`; the PDF attaches it as `certificate-data.json` with `AFRelationship /Data`.
- New download `reports/<id>/versions/<n>/data/` (URL name `reporting:data`), checked against its checksum and audited as `report.data_downloaded`.
- The lot record export adds `files/certificates/<number>-v<n>-data.json` and the check `certificate data file`; `verify_restore` checks the data checksum with the certificates.
