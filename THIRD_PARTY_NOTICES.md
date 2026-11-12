# Third-party software

OpenBGA Fresh CoA LIMS is derived from OpenBGA Roots (<https://github.com/openbga/roots>) at commit `d04a916` and retains its UI assets. Both projects are licensed AGPL-3.0-only. Copyright (C) 2026 BGASoft Inc. and OpenBGA contributors; see [NOTICE](NOTICE). Third-party packages retain their own licenses and notices.
The root LICENSE is the unmodified text retrieved from <https://www.gnu.org/licenses/agpl-3.0.txt>.
`uv.lock` identifies the exact Python distributions; installed distributions retain their license
files in the image. Do not strip those files or the notices in bundled browser assets.
[static/vendor/README.md](static/vendor/README.md) lists each vendored browser asset with its exact
version, files and verified tarball integrity.

| Component | Upstream license / source |
| --- | --- |
| WeasyPrint | BSD-3-Clause; https://github.com/Kozea/WeasyPrint/blob/main/LICENSE |
| Django | BSD-3-Clause; https://github.com/django/django/blob/main/LICENSE |
| Psycopg / psycopg-binary | LGPL-3.0-only; https://www.psycopg.org/psycopg3/docs/basic/install.html |
| Gunicorn | MIT; https://github.com/benoitc/gunicorn/blob/master/LICENSE |
| WhiteNoise | MIT; https://github.com/evansd/whitenoise/blob/main/LICENSE |
| dj-database-url | BSD-3-Clause; https://github.com/jazzband/dj-database-url/blob/master/LICENSE |
| Bootstrap 5.3.8 | MIT; https://github.com/twbs/bootstrap/blob/v5.3.8/LICENSE; retain `static/vendor/bootstrap-5.3.8/LICENSE` and the file headers |
| Popper (@popperjs/core 2.11.8, compiled into the Bootstrap bundle) | MIT; https://github.com/floating-ui/floating-ui/blob/v2.11.8/LICENSE.md; retain `static/vendor/bootstrap-5.3.8/POPPER-LICENSE.md` |
| Bootstrap Icons 1.13.2 (subset in `static/img/icons.svg`) | MIT; https://github.com/twbs/icons/blob/v1.13.2/LICENSE; retain `static/img/icons.LICENSE` |
| htmx 2.0.11 | 0BSD; https://github.com/bigskysoftware/htmx/blob/v2.0.11/LICENSE; retain `static/vendor/htmx-2.0.11/LICENSE` |
| DataTables 3.1.5 (core and Bootstrap 5 integration) / ColReorder 3.1.2 | MIT; https://datatables.net/license/mit; retain `static/vendor/datatables/License.txt` |
| Playwright / pytest-playwright (optional test tools) | Apache-2.0; https://github.com/microsoft/playwright-python/blob/main/LICENSE |
