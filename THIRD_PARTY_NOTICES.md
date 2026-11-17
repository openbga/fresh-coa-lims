# Third-party software

OpenBGA QM LIMS is derived from OpenBGA Roots (<https://github.com/openbga/roots>) at commit `d04a916` and retains its UI assets. Both projects are licensed AGPL-3.0-only. Copyright (C) 2026 BGASoft Inc. and OpenBGA contributors; see [NOTICE](NOTICE). Third-party packages retain their own licenses and notices.
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
| django-otp | Unlicense (public domain dedication); https://github.com/django-otp/django-otp/blob/master/LICENSE |
| Segno | BSD-3-Clause; https://github.com/heuer/segno/blob/master/LICENSE |
| py_webauthn (`webauthn`) | BSD-3-Clause; https://github.com/duo-labs/py_webauthn/blob/master/LICENSE |
| Authlib | BSD-3-Clause; https://github.com/authlib/authlib/blob/main/LICENSE |
| joserfc (installed with Authlib) | BSD-3-Clause; https://github.com/authlib/joserfc/blob/main/LICENSE |
| Requests | Apache-2.0; https://github.com/psf/requests/blob/main/LICENSE |
| Installed with Requests: urllib3, idna, charset-normalizer, certifi | urllib3 MIT (https://github.com/urllib3/urllib3/blob/main/LICENSE.txt); idna BSD-3-Clause (https://github.com/kjd/idna/blob/master/LICENSE.md); charset-normalizer MIT (https://github.com/jawah/charset_normalizer/blob/master/LICENSE); certifi MPL-2.0 (https://github.com/certifi/python-certifi/blob/master/LICENSE) |
| Installed with py_webauthn: cryptography, pyOpenSSL, cbor2, pyasn1, pyasn1-modules | cryptography Apache-2.0 OR BSD-3-Clause (https://github.com/pyca/cryptography/blob/main/LICENSE); pyOpenSSL Apache-2.0 (https://github.com/pyca/pyopenssl/blob/main/LICENSE); cbor2 MIT (https://github.com/agronholm/cbor2/blob/master/LICENSE.txt); pyasn1 and pyasn1-modules BSD-2-Clause (https://github.com/pyasn1/pyasn1/blob/main/LICENSE.rst, https://github.com/pyasn1/pyasn1-modules/blob/main/LICENSE.txt) |
| Bootstrap 5.3.8 | MIT; https://github.com/twbs/bootstrap/blob/v5.3.8/LICENSE; retain `static/vendor/bootstrap-5.3.8/LICENSE` and the file headers |
| Popper (@popperjs/core 2.11.8, compiled into the Bootstrap bundle) | MIT; https://github.com/floating-ui/floating-ui/blob/v2.11.8/LICENSE.md; retain `static/vendor/bootstrap-5.3.8/POPPER-LICENSE.md` |
| Bootstrap Icons 1.13.2 (subset in `static/img/icons.svg`) | MIT; https://github.com/twbs/icons/blob/v1.13.2/LICENSE; retain `static/img/icons.LICENSE` |
| htmx 2.0.11 | 0BSD; https://github.com/bigskysoftware/htmx/blob/v2.0.11/LICENSE; retain `static/vendor/htmx-2.0.11/LICENSE` |
| DataTables 3.1.5 (core and Bootstrap 5 integration) / ColReorder 3.1.2 | MIT; https://datatables.net/license/mit; retain `static/vendor/datatables/License.txt` |
| Tom Select 2.7.0 (including bundled Sifter and microplugin) | Apache-2.0; https://github.com/orchidjs/tom-select/blob/v2.7.0/LICENSE; retain `static/vendor/tom-select/LICENSE` and the file headers |
| Vanilla Calendar Pro 3.4.0 | MIT; https://github.com/uvarov-frontend/vanilla-calendar-pro/blob/v3.4.0/LICENSE; retain `static/vendor/vanilla-calendar-pro-3.4.0/LICENSE` and the file header |
| Playwright / pytest-playwright (optional test tools) | Apache-2.0; https://github.com/microsoft/playwright-python/blob/main/LICENSE |
