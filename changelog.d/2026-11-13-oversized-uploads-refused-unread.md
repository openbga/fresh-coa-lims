---
date: 2026-11-13
type: security
impact: high
title: Oversized uploads are refused before the request is read
area: Whole application
pr: 23
---
A file above the raw-data size limit is refused in the browser when it is chosen, and the server answers an oversized upload with status 413 without reading it. Before, a slow oversized upload kept a server process busy until it had arrived, and it needed no account.

## Technical notes

`core.uploads.UploadSizeMiddleware` is listed ahead of the CSRF check, the first code that reads a submitted form. A multipart request that declares more than `RAW_DATA_MAX_BYTES` plus 1 MiB (room for the form's other fields) gets status 413 and a short page (`templates/413.html`), and its body is left unread. The margin is a constant, not a setting. A file over the limit inside the margin is still stopped by the upload handler and the page returns with the same message as before.

The answer is given before the view runs, so sign-in, role and test-state checks do not apply to it; it changes nothing and shows only the size limit. It relies on the server closing the connection after the answer: Gunicorn's default worker does and reads at most 64 KiB more. A different server, or a proxy that buffers uploads, may still receive the whole request (`docs/operations.md`). No migration and no new setting.
