# Vendored frontend assets

Pinned release files, copied unmodified from the npm registry tarballs. No build step and no
runtime CDN. The application shell `templates/layouts/document.html` loads every file below
except the source maps, which are served only for debugging.

To upgrade a package, download the new tarball (`npm pack <package>@<version>`), check its
`dist.integrity` against the registry (`npm view <package>@<version> dist.integrity`), replace the
files and their licence file, update the paths in `templates/layouts/document.html` and update
this table and `THIRD_PARTY_NOTICES.md`.

| Package | Version | Files (tarball path → repository path) | Licence | Licence file | Tarball integrity (sha512) |
| --- | --- | --- | --- | --- | --- |
| bootstrap | 5.3.8 | `dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js` (+ `.map` files) → `static/vendor/bootstrap-5.3.8/{css,js}/` | MIT | `static/vendor/bootstrap-5.3.8/LICENSE` | `HP1SZDqaLDPwsNiqRqi5NcP0SSXciX2s9E+RyqJIIqGo+vJeN5AJVM98CXmW/Wux0nQ5L7jeWUdplCEf0Ee+tg==` |
| @popperjs/core (inside the Bootstrap bundle) | 2.11.8 | Compiled into `bootstrap.bundle.min.js`; no separate file | MIT | `static/vendor/bootstrap-5.3.8/POPPER-LICENSE.md` | `P1st0aksCrn9sGZhp8GMYwBnQsbvAWsZAX44oXNNvLHGqAOcoVxmjZiohstwQ7SqKnbR47akdNi+uleWD8+g6A==` |
| htmx.org | 2.0.11 | `dist/htmx.min.js` → `static/vendor/htmx-2.0.11/` | 0BSD | `static/vendor/htmx-2.0.11/LICENSE` | `Thx/WtpeOQqSrqBCw/A1cwGJGg4UrVa3+sW0GmrM3p4gJgO89ecH4qtbnyzDDWFvBTqjnIMCgELTNt636dtamA==` |
| datatables.net | 3.1.5 | `js/dataTables.min.js` → `static/vendor/datatables/` | MIT | `static/vendor/datatables/License.txt` | `phu9fVz1cOhD7kZDO5Ztj15qwghCkmdwX5AezLi+PxfMtnFAq0itpewvXzdwdr6bOwPqO2zuXsXWUU5x3wQptw==` |
| datatables.net-bs5 | 3.1.5 | `js/dataTables.bootstrap5.min.js`, `css/dataTables.bootstrap5.min.css` → `static/vendor/datatables/` | MIT | `static/vendor/datatables/License.txt` (identical text) | `eGSe7DVcqqI0RKtrjgzFVqqCZoltJSahAKLCJ0nH0WzSfVclhD8maoGbbz/JJQXky1H9c+vzAnbmAevYRBjxOw==` |
| datatables.net-colreorder | 3.1.2 | `js/dataTables.colReorder.min.js` → `static/vendor/datatables/` | MIT | `static/vendor/datatables/License.txt` (identical text) | `+PckBw8ayHeOXk1qEWMZLzEAHXu4nSVGb5ef7PTFqwYQrPLsZ0xa6A9boUu1se+4xQj/4vPtZ+0Hj3HiIunA3A==` |
| datatables.net-colreorder-bs5 | 3.1.2 | `css/colReorder.bootstrap5.min.css` → `static/vendor/datatables/` | MIT | `static/vendor/datatables/License.txt` (identical text) | `4uBj32P0wHDsCW8+9Goy8fD7HPDUQNANeJqU+2nTkVESDrgU7I4R7PBHi+W9TG84cBixpUptPg8wtzL4t3I0EQ==` |
| tom-select | 2.7.0 | `dist/js/tom-select.complete.js`, `dist/js/tom-select.complete.min.js`, `dist/css/tom-select.bootstrap5.css` (+ `.map` files) → `static/vendor/tom-select/`; the page loads the minified script | Apache-2.0 | `static/vendor/tom-select/LICENSE` | `i/iuTfrzYfGPAILfgPdU9/CCSm8XcnomjO2bHjAcFQPV7od0ghVngjaMfB5x5Agkrpe+49/tK6soegrwWyi6Lg==` |
| vanilla-calendar-pro | 3.4.0 | `index.js` (browser-global build, `window.VanillaCalendarPro`), `styles/layout.css` kept as `layout.css` (layout only; `static/css/controls.css` colours it) → `static/vendor/vanilla-calendar-pro-3.4.0/` | MIT | `static/vendor/vanilla-calendar-pro-3.4.0/LICENSE` | `HLWjzHOWvMIrjI77tXK5bYzp0s5TeBSrZC247STjcTAdWI7kqEwWT6Xvu20vqdwzF498H1Da8l4WpdgVIGtc1Q==` |
| Archivo (Latin subset, wght 400–900, wdth 100–125) | 2.001 | google/fonts `ofl/archivo/Archivo[wdth,wght].ttf`, subset to `static/vendor/archivo-2.001/archivo-latin-wdth-wght.woff2` | OFL-1.1 | `static/vendor/archivo-2.001/Archivo-OFL.txt` | sha256 `820af33b0f9babc4089c013fc824374db5180a1b7731c45455be591ab2926e41` (subset file; not an npm tarball) |
| bootstrap-icons (subset) | 1.13.2 | 93 icons as SVG `<symbol>` elements in `static/img/icons.svg` (paths unmodified, wrapped as a sprite) | MIT | `static/img/icons.LICENSE` | `fAU1Ly3dH7hwRg+CB8EZ0Vl0fF80zgXHeUVJyfUOKzoURr+TbwISbCW5tKUoQLERaWYG2emTCybcPbD96hdD1A==` |

The Popper version is the one Bootstrap 5.3.8 declares (`@popperjs/core` `^2.11.8`; 2.11.8 is the
latest 2.x release). The presentation website (`website/`) copies the Bootstrap CSS (with its licence header) and
`static/css/app.css` at build time and adds no other third-party files.
