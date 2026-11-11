# Third-party software

OpenBGA Qualab is derived from OpenBGA Roots (<https://github.com/openbga/roots>) at commit `d04a916` and retains its UI assets. Both projects are licensed AGPL-3.0-only. Copyright (C) 2026 BGASoft Inc. and OpenBGA contributors; see [NOTICE](NOTICE). Third-party packages retain their own licenses and notices.
The root LICENSE is the unmodified text retrieved from <https://www.gnu.org/licenses/agpl-3.0.txt>.
`uv.lock` identifies the exact Python distributions; installed distributions retain their license
files in the image. Do not strip those files or the notices in bundled browser assets.

| Component | Upstream license / source |
| --- | --- |
| WeasyPrint | BSD-3-Clause; https://github.com/Kozea/WeasyPrint/blob/main/LICENSE |
| Django | BSD-3-Clause; https://github.com/django/django/blob/main/LICENSE |
| Psycopg / psycopg-binary | LGPL-3.0-only; https://www.psycopg.org/psycopg3/docs/basic/install.html |
| Gunicorn | MIT; https://github.com/benoitc/gunicorn/blob/master/LICENSE |
| WhiteNoise | MIT; https://github.com/evansd/whitenoise/blob/main/LICENSE |
| dj-database-url | BSD-3-Clause; https://github.com/jazzband/dj-database-url/blob/master/LICENSE |
| Bootstrap | MIT; retain bundled license header/file |
| HTMX | BSD-2-Clause; retain bundled license header/file |
| Tom Select (including bundled Sifter) | Apache-2.0; https://github.com/orchidjs/tom-select/blob/v2.7.0/LICENSE; retain bundled license and headers |
| Chart.js 4.6.1 / bundled @kurkle/color 0.3.2 | MIT; https://github.com/chartjs/Chart.js/blob/v4.6.1/LICENSE.md; retain both license files under static/vendor/chartjs-4.6.1/ |
| DataTables / ColReorder | MIT; https://datatables.net/license/mit; retain bundled License.txt |
| Playwright / pytest-playwright (optional test tools) | Apache-2.0; https://github.com/microsoft/playwright-python/blob/main/LICENSE |

