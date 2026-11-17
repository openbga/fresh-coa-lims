---
date: 2026-11-17
type: changed
impact: medium
title: Certificate of analysis and lot record PDFs use the new design
area: Certificates
link: reporting:list
pr: 46
---
The certificate of analysis and the exported lot record share one print layout that stays readable in black and white. Every regulated element is kept, and no new sentence is printed on the certificate. Certificates already issued are stored files and keep their original bytes.

## Technical notes

Both PDFs share one print stylesheet. A test downloads a certificate issued before the change and compares it byte for byte with the stored copy; 64 certificate elements were checked against the checklist. The renderer (`reporting/render.py`) loads only the vendored font and status glyphs, by exact URL, through a fetcher allowlist.
