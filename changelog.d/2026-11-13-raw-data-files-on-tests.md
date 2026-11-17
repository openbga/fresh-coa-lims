---
date: 2026-11-13
type: added
impact: high
title: Attach raw-data files to a test
area: Testing
link: analytical:test_list
pr: 22
---
A raw-data file can be attached to a test. It is stored with its SHA-256 checksum, never changes and is returned unchanged on download.

## Technical notes

- Raw-data files: a file can be attached to a test, is stored with its SHA-256 checksum, never changes and is returned unchanged on download. `RAW_DATA_MAX_BYTES` sets the largest accepted file and `RAW_DATA_TOTAL_MAX_BYTES` an optional ceiling for all files together. A larger file is refused in the browser before it is sent, and the server answers an oversized upload with status 413 without reading it.
