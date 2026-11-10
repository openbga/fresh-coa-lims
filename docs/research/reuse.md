# Reuse plan: Open Roots IQ → Open Qual IQ

Source: `/Users/gabriel/work/vibe-roots-iq` (read-only; 24 commits, branch main). Analysed 2026-11-10 from
the files cited below. No code was changed. "ORIQ" = Open Roots IQ (environmental LIMS), "OQIQ" = Open Qual IQ.

Legend: **as-is** = copy and rename only; **adapt** = keep structure, change domain content; **drop** = leave out of v1
(may be mined later as a pattern reference).

## 1. Summary

| Area | Verdict | One-line reason |
| --- | --- | --- |
| Stack, tooling, versions | as-is | Generic Django 5.2 / PG 17 / Bootstrap+HTMX baseline (`pyproject.toml`, `docs/architecture.md`) |
| Dockerfile, `.dockerignore`, `compose.yaml` | as-is (rename DB/user) | Nothing domain-specific except `vibe_roots` names |
| `render.yaml` | adapt (rename) | Names, DB identifiers, TIME_ZONE; see §6 |
| CI `.github/workflows/checks.yml` | adapt (rename) | 3 jobs are generic; DB names and image tag are ORIQ's |
| `config/` | as-is (+ small edits) | Settings are generic; defaults mention `vibe`/`vibe_roots` and `America/New_York` |
| `templates/` + `static/` | as-is + adapt | The design system is the biggest reuse asset; rebrand mark/name only; nav and a few labels adapt |
| `accounts` | as-is | Roles/permission model generic; role names need review for QC lab |
| `core` | as-is (+ adapt nav/dashboard) | Audit, grids, form dialog, health, request log are generic |
| `catalog` | adapt | Structure (method/analyte/test) fits QC, but `matrix` choices and "analyte/CAS" are environmental |
| `receipt` | adapt (heavy) | Custody/sample/container/labels/storage are reusable; clients/COC/orders/subcontract are environmental-flavoured |
| `analytical` | adapt (heavy, selective) | Result/revision/QC/review/import core reusable; MDL, preservation/holding-time, preparation are environmental |
| `reporting` | adapt (core) / drop (EDD) | Immutable versioned PDF reports reusable; `reporting/edd/*` NYSDEC is regulatory-environmental |
| `commercial` | drop for v1 (candidate) | Price lists, quotes, client submissions: not core to in-house manufacturing QC; revisit by research |
| `laboratory` | adapt | Equipment, materials/lots, training, nonconformance map directly to manufacturing QC |
| `tests/`, `e2e/` | adapt | Harness/fixtures/UI-standards tests reusable; domain tests move with their apps |
| `docs/` | adapt | Keep structure and rules; rewrite domain content (do not copy environmental rules) |

Size reference (non-test, non-migration Python lines): analytical ≈11.6k, reporting ≈4.9k (988 in `edd/nysdec.py`),
receipt ≈4.8k, laboratory ≈4.6k, commercial ≈3.5k, core ≈1.4k, catalog ≈1.1k, accounts ≈0.7k. `static/css/app.css` is 3,263 lines;
`static/js/*` ≈1.5k lines. 617 pytest test functions plus 15 browser journeys in `e2e/`.

## 2. Per-module analysis

### accounts — as-is
- Files: `accounts/models.py` (custom `User` with `email` unique, nullable `client` FK, permission `authorize_release`),
  `roles.py` (group-name roles: admin, custodian, analyst, reviewer, approver, project_manager; `effective_roles`,
  `require_role`, `can_authorize_release`), `adapter.py` (closed signup), `setup.py` / `setup_lab` command, `admin.py` (313 lines).
- Generic: custom user from first migration, group roles, explicit release capability separate from admin, invite-only
  allauth with MFA. The "nobody reviews their own results" and "superuser ≠ release" rules fit QC release as well.
- Specific/coupling: `User.client` FK targets `receipt.Client` (string reference) — couples accounts to receipt and to the client
  portal concept. Role names (custodian, project_manager) are lab-intake terms; manufacturing QC may want e.g. sampler/inspector,
  QC analyst, QC reviewer, QA approver. Keep the mechanism, rename in one place (`ROLES`).
- Decision for OQIQ: keep `client` only if an external-customer portal remains in scope (e.g. supplier/customer COA recipients); otherwise
  replace with an optional external-party FK. Decide before the first migration.

### core — as-is (adapt dashboard/navigation)
- Reusable: `models.py` (`Lab` singleton, `AuditEvent` with actor/before/after/reason), `audit.py`, `concurrency.py`, `grids.py`,
  `form_dialog.py` + `form_surfaces.py` + `context_processors.py` (dialog infrastructure), `request_logging.py`, `retention.py`,
  health/ready views, `seed_demo` command skeleton, DB triggers making `AuditEvent` immutable (`core/migrations/0002_audit_immutable.py`).
- Adapt: `templatetags/navigation.py` (473 lines) is the single route→sidebar-item declaration and carries every ORIQ route;
  `form_surfaces.py` lists ORIQ route names → dialog size (must be re-declared per app); `views.dashboard` and `templates/core/*`
  (work queues), `Lab` defaults (`timezone="America/New_York"`).
- Coupling risk: `core` imports from every domain app (accounts 6, receipt 5, laboratory 4, commercial 3, analytical 2, reporting 2, catalog 1)
  — dashboard/navigation/form-surface registries sit "above" the apps. Moving them to a thin `config`/`workspace` layer is optional; at least
  keep one declaration site each (navigation, form surfaces) as ORIQ does.

### catalog — adapt
- `Method` (code+version unique), `Analyte` (name, `cas_number`), `TestDefinition` (method × analyte × matrix, unit, reporting_limit Decimal(20,8)).
- Generic: versioned methods, Decimal limits, unique constraints. Specific: `matrix` choices water/wastewater/soil; "analyte" and CAS number
  (chemical). Likely QC mapping: Method → test method/SOP version, Analyte → characteristic/parameter, matrix → material/product/stage, plus
  specification limits (min/max/target) which ORIQ models only as a single reporting limit — new requirement, research-driven.
- Small (1.1k lines) and imported by receipt/analytical/commercial: change early and deliberately; it is a shared contract.

### receipt — adapt (heavy)
- Models: `Client, ClientContact, Project, Order, Sample, Container, RequestedTest, CustodyEvent`; plus `storage_models`, `subcontract_models`.
- Reusable patterns: accession numbering (`VR-000001`, sequence trigger in `receipt/migrations/0004_accession_sequence.py`), sample + container +
  requested-test structure, immutable custody events with actor, corrections with reason and prior linkage (`corrections.py`), labels/Code 128
  (`labels.py`, python-barcode), storage locations, scheduling, disposition/disposal holds, receipt/sample list filters (`filters.py`, `lists.py`).
- Environmental-specific: Client/Project/Order as chain-of-custody (COC) for external field sampling, collector/location/collection-type fields,
  field-sample "receipt observations", subcontract (external lab) sources. Manufacturing QC samples come from lots/batches/production lines,
  incoming material, or in-process checks — the intake entity changes (lot/batch/work-order/supplier) even though sample/container/custody mechanics stay.
- Coupling: receipt imports analytical 14× and reporting 2× (circular-ish; e.g. holding-time/work status), and analytical/reporting/commercial/laboratory
  import receipt. Receipt is the hub — `Sample` is the anchor FK for everything. Keep `Sample` and its status machine stable; rework `Order/Client/Project`.
- Recommendation: v1 keeps Sample/Container/CustodyEvent/labels/storage/corrections/disposition; replaces Client/Project/Order with the OQIQ intake
  concept; drops subcontract until research shows need.

### analytical — adapt (heavy, selective)
- Models (20): `Qualifier, HoldingTimeRule, QCRequirement, QCLimit, Batch, QCSample, QCMeasurement, QCCorrectiveAction, Result, ResultRevision,
  MDLStudy/Observation/Calculation, ImportProfile, PreservationRule/Decision, PreparationRequirement, PreparedAliquot, PreparedTest`.
- Reusable core: `Result` + immutable `ResultRevision` (trigger migration `0002_revision_immutability.py`), `Batch` worklists, `QCSample/QCMeasurement/
  QCLimit/QCRequirement` with corrective action, independent review/release with no self-review, `qualifiers`, operator-mapped CSV import
  (`importing.py`, `import_profiles.py`, `parsing.py`), control charts (`charts.py`, Chart.js), `stats.py`/SciPy for limits, Decimal handling.
- Environmental-specific: MDL studies (`mdl*.py`, EPA-style detection limits), holding-time + preservation rules (`holding.py`, `preservation*.py`),
  preparation aliquots (`preparation*.py`), `synthetic_dataset.py`/`seed.py` water/soil data. Some have QC analogues (shelf life/expiry, retest
  dates; sample conditioning; method detection/quantitation limits in instrumental QC) — decide per research, not by default.
- Coupling: the 1.5k-line `views.py` and 1.3k-line `services.py` mix core and environmental flows; analytical imports catalog 11×, receipt 8×,
  core 15×. Extract by deleting modules (mdl, preservation, preparation) and their routes in `navigation.py`/`form_surfaces.py`, plus the checks they add to
  release gating in `services.py` (release checks include preservation and preparation conditions — README "Every test in a new report issue ... preservation evidence").
  Expect release-gate edits to be the riskiest change.

### reporting — adapt (core) / drop (EDD)
- Reusable: `Report/ReportVersion/ReportFile` — immutable snapshot, stored PDF bytes + hash, amendment versions, release permission check, lock-and-recheck
  at release (`services.py`, `pdf.py` WeasyPrint, trigger migration `0002_release_immutability.py`), report preview + portal download (`portal_views.py`).
  This maps well to a Certificate of Analysis / test report.
- Specific: `report_preview.html` content (`content.py`, 637 lines) is environmental (preservation/qualifier/limit narrative), and the whole `reporting/edd/`
  package (NYSDEC EDD: 8 files, ~1.9k lines + 3 models + migration `0003_nysdec_exports.py`) — drop.
- Coupling: reporting imports analytical 15× and receipt 13× (snapshot gathers everything). Replace snapshot content builders; keep the transaction/hash/versioning code.

### commercial — drop for v1 (candidate)
- Models: price lists, versioned quotes, client submissions (COCs submitted pre-arrival). Selling testing services to external clients; in-house
  manufacturing QC rarely needs it. Imports receipt 10×. Dropping it removes ~3.5k lines, 3 migrations, `portal_urls`, and the "Sales" sidebar group.
  Reconsider only if research finds supplier/customer submission workflows. Pattern value: versioned documents (`quotes.py`) mirrors report amendments.

### laboratory — adapt
- Models: `Material, MaterialLot, StockMovement, Equipment, Nonconformance` + training records (`training*.py`), `EvidenceMixin`.
- Highly relevant to manufacturing QC (reagent/standard lots and expiry, equipment calibration/maintenance, analyst qualification, nonconformance/CAPA
  precursor). Mostly generic already; only `README`-level wording and seed data are environmental. Lowest-risk domain app to keep: it imports analytical 2×,
  receipt 4×, catalog 2×.

### templates / static — the design system (see §3) — as-is + adapt
- As-is: `templates/layouts/*`, `templates/includes/*` (28 shared partials), `templates/django/forms/*` (form renderer), `templates/allauth/*`,
  `templates/400/403/404/500.html`, `static/css/app.css`, `static/css/admin.css`, `static/js/*`, `static/vendor/*` (+ README with integrity hashes),
  `static/img/icons.svg` (Bootstrap Icons subset, MIT).
- Adapt: brand name defaults in `includes/brand.html`, `layouts/document.html` title/offcanvas text, `static/img/mark.svg` (new mark; the current one is a water
  drop), admin templates, 400/403/404/500, `includes/nav_staff.html` (groups Sales/Intake/Bench/Release…), `entrance_scene.html` (illustration is ORIQ branding).
  Hex colours are ORIQ's "field notebook" palette: decide whether OQIQ keeps it (brief says reuse look and feel; yes by default, with a distinct mark/name).
- Per-app templates (`receipt/templates/…`, `analytical/templates/…`, etc.) travel with their app.

### tests / e2e / config / infra
- `tests/` generic and reusable: `conftest.py` fixtures (`staff`, `receipt_data` is domain), `test_ui_standards.py` (template lint), `test_navigation.py`,
  `test_theme_markup.py`, `test_form_dialog.py`, `test_form_surfaces.py`, `test_history_guards.py`, `test_request_logging.py`, `test_timezone_contract.py`,
  `test_admin_access.py`, `test_auth.py`. Domain tests (custody, receipt workflow, requested-test selection, MDL, demo seed) adapt/drop with their apps.
- `e2e/` (Playwright, separate `pytest.ini`): `conftest.py`, `helpers.py`, `test_form_dialog.py`, `test_theme.py`, `test_sample_list.py`, `test_access.py`,
  `test_admin_access.py`, `test_screenshots.py` are generic; keep one journey per page type and the contrast check for both themes.
- `config/`: `settings.py` (152 lines, env-driven), `urls.py`, `logging.py`, `wsgi.py`. As-is; edit default DB URL and `INSTALLED_APPS`/urls to the retained apps.
- Hygiene files: `.gitignore` (ignores `.local/`, `.env*`, `staticfiles/`), `.dockerignore`, `.python-version`, `LICENSE` (GPL-3.0), `THIRD_PARTY_NOTICES.md` (retain,
  update name), `AGENTS.md`/`CLAUDE.md` (rewrite for OQIQ; see ORIQ rules 1–11 as a template).

## 3. UI design system (to reproduce faithfully)

Authoritative sources: `docs/ui-standards.md` (322 lines, rules), `static/css/app.css` (tokens + components), `templates/layouts/document.html` (block contract),
`templates/includes/*` (one partial per concept), `core/templatetags/navigation.py` (nav declaration), `static/js/*`. Copy these files verbatim first, rebrand second.

**Libraries (all vendored, pinned, no CDN, no build step):** Bootstrap 5.3.8 (CSS + bundle JS), HTMX 2.0.11, DataTables 3.1.5 (Bootstrap 5 adapter + ColReorder; used only
to show/hide/reorder columns — server does sorting/filtering/paging), Tom Select (requested-tests picker, loaded only where needed), Chart.js 4.6.1 (reads CSS tokens).
Provenance/integrity in `static/vendor/README.md`.

**Theme: "field notebook"** (light/dark via `data-bs-theme`, set pre-paint by `static/js/theme-init.js`; print always light):
- Token namespace `--vr-*` mapped onto Bootstrap's `--bs-*` (app.css "Tokens" and "Derived tokens and the Bootstrap mapping"). Rename the prefix to `--oq-*` / `oq-` classes
  only with a global replace plus `tests/test_ui_standards.py`/`test_theme_markup.py` updates; prefix change is optional and risky — recommend keep `vr-` initially or do a scripted rename in one commit.
- Light palette (examples): paper `#ffffff`, rule `#eef3f0`, margin `#e07a74`, surface-2 `#f2f6f4`, band/top bar `#e5efe9`, border `#c8d4cd`, border-strong `#7c8b81`, text `#15271d`,
  muted `#4f5f55`, ink (primary) `#1b3a27`, pen (links/focus) `#0a6474`, highlighter `#ffe08a` / wash `#fff4c7` / edge `#a87400`. Dark: paper `#0f201a`, surface `#132820`, band `#1b382d`,
  text `#e3ede7`, ink `#cfe5d6`, amber highlighter, margin `#d9645c`.
- Seven stamp tones `neutral, info, progress, success, warning, danger, hold`, each `-text/-bg/-border`; used only by `includes/status.html` and notices.
- Type: system sans for reading; system monospace (small caps, wide tracking) for labels (table headers, fact labels, sidebar groups, breadcrumbs); mono normal case for data
  (identifiers, dates, counts, numbers). Desktop density smaller; phones 16px.
- Shape: square corners (controls 2px, panels/dialogs 0), hierarchy by rules and space not shadows; menus/dialogs get a hard offset; table header on a full-weight ink rule, rows on hairlines.
- Devices: quad-ruled paper sheet (hazed, fixed under a sage top bar), red margin rule beside the sidebar, highlighter stroke for current sidebar item/section tab, stamp status, numbered
  panel headings (1.0, 2.0) on record pages, record foot line, dateline above overviews, struck-through prior values in history, punched-sheet sign-in beside an illustration (`entrance_scene.html`).
- Accessibility: WCAG 2.2 AA contrast both modes (text 4.5:1, boundaries/focus 3:1), 2px pen focus outline, `prefers-reduced-motion`, skip link, `aria-current`; contrast report was kept in `.local/` (not tracked).

**Shell & layout:** `layouts/document.html` — skip link, sage top bar (menu button <lg, brand, lab name, sample lookup form, theme menu, user menu), `.vr-shell` with `.vr-sidenav` (offcanvas below lg,
static rail from lg) + `main.vr-main#main`. Block contract: `title, extra_css, body_class, body, topbar, sidenav, page_header, page_dateline, breadcrumbs, page_heading, page_meta, page_intro,
page_actions, content, record_foot, extra_js`. Other layouts: `portal.html` (top nav, no sidebar), `entrance.html`, `error.html`, `form_fragment.html` (dialog body).

**Page types** (ui-standards §2): List, Record, Form (dialog), Action form (dialog), Entry grid (wide dialog), Overview, Document. Each fixes header, breadcrumbs and the primary action.

**Shared components (one include per job):** `status`, `messages`, `breadcrumbs`, `section_tabs`, `page_toc`, `grid_toolbar` (+ `grid_search`, `filter_chips`, `grid_columns_button`,
`grid_columns_dialog`), `sort_header`, `pagination`, `empty_state`, `select_all`, `history_item`, `form_errors`, `field`, `form_dialog`, `confirm_dialog`, `brand`, `icon`
(SVG sprite `static/img/icons.svg`), `nav_link`/`nav_staff`, `theme_menu`, `user_menu`, `dateline`, `record_foot`, plus `dl.vr-facts`. Buttons: primary/outline-secondary/link/outline-danger, `btn-sm` in rows.
Wording rules (ui-standards §9: `New <thing>`, `Add`, `Record`, `Change`, `Correct`, `Cancel`, sentence case) travel as-is.

**HTMX / progressive-enhancement patterns:**
- `<meta name="htmx-config">` in `document.html`: `includeIndicatorStyles:false`; response handling: 204 no swap, 2xx/3xx swap, **422 swaps** (validation errors re-render), other 4xx/5xx raise error.
- CSRF through `hx-headers='{"X-CSRFToken": …}'` on `<body>`.
- Editing happens in one shared Bootstrap modal (`templates/includes/form_dialog.html`, `static/js/form-dialog.js`, 604 lines): direct URL opens the same dialog; server-rendered full page is the
  no-JS fallback. `core/form_surfaces.py` maps route names → dialog size (`lg`/`xl`); `core/context_processors.py` switches layout to `layouts/form_fragment.html` when request header `X-VR-Form: 1`;
  `core/form_dialog.py` middleware turns 302/303 into 204 + `HX-Location` (next form) or `HX-Redirect` (record) so Django messages survive; `Vary: X-VR-Form`.
  Focus moves in/returns to opener; Escape/Cancel with unsaved input offers Keep editing/Discard; maximize for entry grids; htmx 30s request timeout.
- `static/js/app.js` handles `htmx:load`, `htmx:responseError`, `htmx:sendError` (visible recovery messages) and child-row add/remove (`htmx.process`).
- Grids: `static/js/grid.js` enhances server-rendered tables on `htmx:load` (column order/visibility in browser storage, no row API). `test-picker.js` Tom Select on `htmx:load`/`afterSettle`.
- The rest of the app is mostly plain Django forms/links; only a handful of `hx-*` attributes appear in templates (`hx-post`, `hx-get`, `hx-target`, `hx-swap`, `hx-sync`, `hx-push-url`,
  `hx-replace-url`, `hx-encoding`, `hx-request`). Templates also avoid inline style/colours (enforced by `tests/test_ui_standards.py`).

**Enforcement to port:** `tests/test_ui_standards.py` (banned patterns), `tests/test_navigation.py` (every HTML route marks exactly one nav item, label = list title), browser contrast check (`e2e/test_theme.py`).

## 4. Generic vs environmental-specific

| Generic (keep) | Environmental-specific (replace/drop) |
| --- | --- |
| Single-lab singleton, AuditEvent, immutable-history DB triggers, row-lock/version concurrency | NYSDEC EDD export, mappings, readiness |
| Roles via groups + explicit release permission; allauth invite-only + MFA | Water/wastewater/soil matrices; CAS numbers; EPA-style MDL studies |
| Sample/container/custody events, labels (Code 128), storage, corrections with reason | Holding-time and preservation rules/decisions; preparation aliquots |
| Method/test/analyte catalog with versions, Decimal limits and units | COC orders, client submissions, quotes/price lists, subcontract labs |
| Result + revision, batches/worklists, QC samples/limits/control charts, no-self-review, CSV import | Synthetic water/soil seed data; `VR-` accession prefix; America/New_York defaults |
| Versioned immutable PDF reports with hash and amendments; client/portal downloads | Report narrative content (preservation/qualifier language) |
| Equipment, materials/lots, training, nonconformance | "Open Roots IQ" branding, water-drop mark, field-notebook illustration |
| Health/ready, request logging, structured logging, time-zone contract | `Lab.timezone` default, `TIME_ZONE` default |

## 5. Migration strategy

**Recommendation: fresh repository seeded from a copy of the selected files, history not carried (single initial commit), with fresh migrations. Not a fork.**

| Option | Pros | Cons | Verdict |
| --- | --- | --- | --- |
| Fork / keep history | Blame and provenance retained | ORIQ's 24 commits and `.local/`-derived history include environmental decisions and deployment/service churn; two diverging products share a remote; fork relationship invites accidental cross-pollination (brief: do not carry conventions/data between projects); private→public/GPL history hygiene | No |
| Fresh repo, squashed copy | Clean domain history; no coupling to upstream; migrations restart; simple Render/GitHub identity | Loses blame; later upstream fixes must be cherry-picked by hand | **Yes** |

Steps:
1. Copy selected paths with `rsync` excluding `.git`, `.local/`, `.venv`, `.ruff_cache`, `.pytest_cache`, `staticfiles/`, `.DS_Store`, `__pycache__`, `.env*`. Do **not** copy `.local/` (contains dev logs, `render-demo-access.txt`, deploy JSON, screenshots).
2. Record provenance in README/`THIRD_PARTY_NOTICES.md`: derived from Open Roots IQ (GPL-3.0-only; keep the unmodified `LICENSE` and notices; both are the same licence so no conflict). Note ORIQ source commit `d04a916`.
3. Global rename: `open-roots-iq`→`open-qual-iq`, "Open Roots IQ"→"Open Qual IQ", `vibe_roots`/`vibe`→`open_qual`/`oqiq` (compose, `.env.example`, settings default DB URL, CI), `VR-` accession prefix (decide), `vri-` backup names, `vri_restore_check`.
   Leave the `vr-` CSS prefix initially unless renamed in a dedicated scripted commit.
4. **Fresh migrations:** because domain models change, delete all `*/migrations/0*.py` for kept apps and regenerate `0001_initial` per app after models stabilise. Reasons: ORIQ migrations encode environmental history and
   data-migration steps; no deployed OQIQ data to preserve. Caveat — hand-written `RunSQL` must be re-created: immutability triggers (`core/0002_audit_immutable`, `analytical/0002_revision_immutability`, `0003_mdl_records`,
   `0007_preservation_records`, `0008_preparation_identity`, `reporting/0002_release_immutability`, `0004_external_result_versions`, `0003_nysdec_exports`), accession sequence (`receipt/0004_accession_sequence`), and the single-lab constraint.
   Keep them as explicit `0002_*` migrations in each app (RunSQL with reverse) so `makemigrations --check` stays clean. `accounts` must be created in the first migration (custom User); `tests/test_history_guards.py` verifies triggers — port it before deleting old migrations.
5. Stage the work: (a) infrastructure + shell + design system + accounts/core + tests, green on an empty domain; (b) catalog + laboratory; (c) intake/samples + analytical + reporting per research-driven requirements. Drop commercial and `reporting/edd` at step (a).
6. Gate after each stage with the ORIQ commands (§7). Only one owner edits `catalog`, `navigation.py`, `form_surfaces.py`, lockfile and migrations at a time (hubs).

**Coupling risks to manage**
| Risk | Where | Mitigation |
| --- | --- | --- |
| Receipt is a hub: analytical→receipt 8, reporting→receipt 13, commercial→receipt 10, laboratory→receipt 4; receipt→analytical 14 (cycle) | `Sample` FK everywhere | Freeze `Sample`/`Container`/`CustodyEvent` contract before porting other apps; use string FKs; remove receipt→analytical imports where dropping holding/preservation |
| `User.client → receipt.Client` | accounts, core context | Decide portal/external-party model first |
| Release gate in analytical/reporting services mixes env checks (preservation, preparation, holding) | `analytical/services.py`, `reporting/services.py` | Re-derive gate from QC research; keep lock/recheck/snapshot mechanics and tests |
| Central registries (nav, form surfaces, dashboard) list every route | `core/templatetags/navigation.py`, `core/form_surfaces.py`, `core/views.py` | Edit registries as the final step of each app port; `test_navigation.py` catches omissions |
| Hand-written SQL triggers | migrations listed above | Re-create explicitly; run history-guard tests on PostgreSQL |
| Strict WhiteNoise manifest storage | tests render templates | Run `collectstatic` before pytest (as CI does) |
| Domain data baked into tests/seed (water/soil, NYSDEC, `VR-`) | tests, `seed_demo`, `analytical/synthetic_dataset.py` | Rewrite with synthetic manufacturing data; do not port env fixtures |

## 6. Deployment on Render (what exists and what to rename)

From `render.yaml`, `Dockerfile`, `config/settings.py`, `core/views.py`, README "Deploy to Render", `docs/architecture.md`.

| Item | ORIQ value | OQIQ action |
| --- | --- | --- |
| Web service name | `open-roots-iq` (runtime docker, plan `1c-2g`, region virginia, `autoDeployTrigger: "off"`) | New service `open-qual-iq` |
| Database name / id | `vibe-roots-iq-db`; `databaseName: vibe_roots`; `user: vibe_roots`; plan `0.5c-1g`; PG major `17`; disk 5 GB; `ipAllowList: []` | New DB `open-qual-iq-db`; `databaseName`/`user`: `open_qual` (or similar); keep PG 17, empty allow list |
| Health check | `healthCheckPath: /health/` (process; `{"status":"ok"}`); `/ready/` does `SELECT 1`, 503 on failure | Keep both routes |
| Pre-deploy | `preDeployCommand: python manage.py migrate --noinput` | Keep; with fresh migrations the first deploy migrates an empty DB |
| Build | Docker build runs `collectstatic` (`DEBUG=true` for that step), non-root `app` uid 10001 with `/home/app/.ssh` (0700) for Render SSH shell | Keep (CI asserts it) |
| Start | `gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 60 --error-logfile -` | Keep |
| Blueprint env vars | `DATABASE_URL` (fromDatabase connectionString), `SECRET_KEY` (generateValue), `DEBUG=false`, `WEB_CONCURRENCY=2`, `TIME_ZONE=America/New_York`, `EMAIL_BACKEND=…dummy.EmailBackend` | Keep structure; set `TIME_ZONE` per OQIQ decision |
| Env read by app, not in blueprint | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (custom domains), `RENDER_EXTERNAL_HOSTNAME` (auto-set by Render → host + `https://` origin trusted), `TEST_DATABASE_NAME`, `REPORT_SYNTHETIC_DATA_NOTICE` (default true), SMTP: `EMAIL_HOST/PORT/USE_TLS/HOST_USER/HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `DEMO_PASSWORD` (seed only) | Document in new `.env.example`; keep `REPORT_SYNTHETIC_DATA_NOTICE=true` |
| Security settings (non-DEBUG) | `SECURE_SSL_REDIRECT`, secure cookies, `SECURE_PROXY_SSL_HEADER=X-Forwarded-Proto`, HSTS 3600, `X_FRAME_OPTIONS=DENY` | Keep |
| Instance setup | One-time `python manage.py setup_lab --lab-name … --admin-username … --admin-email …` in service shell; no seed/reset on deploy | Keep; rename lab wording |
| README button | `https://render.com/deploy?repo=https://github.com/gabalint/open-roots-iq` | Point to the new repo once it exists |

New-service rule: ORIQ comment says "Existing database identifiers stay stable to preserve deployed data" — that is why the DB is still `vibe-roots-iq-db`; OQIQ must **not** reuse those identifiers or the ORIQ service/DB: create new
service `open-qual-iq` + DB `open-qual-iq-db`. Plans are paid (about $7 web + $6 DB floor at Hobby per `docs/architecture.md`, checked 2026-11-08; `1c-2g`/`0.5c-1g` are above that); per the brief, spending needs coordinator/user approval — propose
smaller starter plans or keep ORIQ's and ask. `ipAllowList: []` and `autoDeployTrigger: off` keep exposure and cost low. `.local/deploy/` and `.local/render-demo-access.txt` in ORIQ hold service JSON and demo credentials: do not copy.

Other renames outside Render: Docker image tag `open-roots-iq:ci`, CI env file `vibe-smoke.env`, DB users in CI (`vibe`, `vibe_ci`), `compose.yaml` (`vibe`/`vibe_roots`, port 55432), `.env.example` DATABASE_URL.

## 7. Checks, commands and versions

| Item | ORIQ value (source) |
| --- | --- |
| Python | `requires-python >=3.14,<3.15`; `.python-version` 3.14.10; Docker `python:3.14.10-slim-bookworm` |
| Package manager | uv 0.13.7 (`ghcr.io/astral-sh/uv:0.13.7`, `setup-uv` pinned), `uv.lock`, `uv sync --frozen` |
| Django / auth | Django `>=5.2.19,<5.3` (LTS); django-allauth[mfa] `>=65.21.1,<66` |
| DB | PostgreSQL 17; psycopg[binary] `>=3.3.8,<4`; dj-database-url `>=3,<4` |
| Serving | gunicorn `>=26.2,<27`; whitenoise `>=6.12,<7` (`CompressedManifestStaticFilesStorage`) |
| Documents / stats | weasyprint `>=70,<71` (needs libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz-subset0, fonts-dejavu-core); python-barcode `>=0.16.1,<0.17`; scipy `>=1.18.1,<1.19` (drop if no stats need) |
| Dev | pytest `>=9,<10`, pytest-django `>=4.14,<5`, ruff `>=0.17.4,<0.18`; e2e group pytest-playwright `>=0.10,<0.11` (Chromium shell; poppler-utils for PDF assertions) |
| Ruff | line-length 100, target py314, select E,F,I,UP,B; migrations ignore E501 |
| Pytest | `DJANGO_SETTINGS_MODULE=config.settings`, `testpaths` list per app + `tests`; e2e uses `-c e2e/pytest.ini e2e` |
| Frontend | Bootstrap 5.3.8, HTMX 2.0.11, DataTables 3.1.5 (+ColReorder), Chart.js 4.6.1, Tom Select (vendored); Bootstrap Icons 1.13.2 subset |

Commands (README, `.github/workflows/checks.yml`, AGENTS.md rule 9):
```sh
uv sync --frozen
docker compose up -d db                      # PG 17 on 127.0.0.1:55432
export DEBUG=true DATABASE_URL=postgresql://…/…
uv run ruff check . && uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput    # before template tests (strict manifest)
REQUIRE_WEASYPRINT=1 uv run pytest
uv run --group e2e playwright install --only-shell chromium
REQUIRE_WEASYPRINT=1 uv run --group e2e pytest -c e2e/pytest.ini e2e
```
macOS: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` and direct `.venv/bin/python -m pytest`. Parallel workers: `TEST_DATABASE_NAME=test_<name>` (must start with `test_`, differ from the DB name).
PostgreSQL is mandatory for tests (locks, triggers).

CI (3 jobs, all `on: [push, pull_request]`, actions pinned by SHA): **application** (PG 17 service; apt PDF libs; ruff check+format; `manage.py check`; `makemigrations --check`; `migrate`; `collectstatic`; `pytest`),
**browser** (e2e group; Playwright Chromium; poppler; isolated DB), **container-smoke** (docker build; migrate + check inside image; WeasyPrint PDF and SciPy smoke; non-root/SSH-dir assertions; start gunicorn; curl `/ready/`, `/health/`,
`/accounts/login/`, `/static/admin/css/base.css` with `X-Forwarded-Proto: https`). Never publishes or deploys. Reuse as-is with renames; drop the SciPy line if SciPy is dropped.

## 8. Decisions needed / assumptions

| Item | Default assumption (mine) | Owner |
| --- | --- | --- |
| Keep `vr-` CSS prefix at first | Yes; scripted rename later if desired | Coordinator |
| Drop `commercial` and `reporting/edd` for v1 | Yes; holding-time/preservation kept as rule-pattern reference (§9) | Coordinator (scope) |
| Keep client portal / `User.client` | Pending research; decide before first migration | Product research |
| Accession prefix, roles, `TIME_ZONE`, matrix → material taxonomy | Placeholders until research | Product research |
| Render plans and spending | Resolved by user 2026-11-10: `1c-2g` web, `0.5c-1g` DB, 5 GB; provision after a passing integrated build (§9) | Coordinator |
| Keep GPL-3.0-only | Yes (derivative of GPL-3.0-only work; retain LICENSE and notices) | Coordinator (legal) |
| Palette/mark | Keep palette; new mark/name | Coordinator |

Gaps in this analysis: I did not read every view/template or run any ORIQ checks (read-only task); per-app line counts and import counts come from `wc`/`grep` on non-test, non-migration `*.py`;
the claim that the mapped release gate includes preservation/preparation checks is from README and `docs/architecture.md`, not a full read of `analytical/services.py`.

## 9. Update 2026-11-10: one system for all manufacturing QC segments

User decision (`.local/briefs/common.md`): a single product serves pharma/biotech cGMP, supplements, food, chemical/industrial and devices. Segment rules are **configuration**, not forks or per-segment apps. Audit trail and PIN-based electronic signatures are core. Effects on the reuse plan:

| Topic | Effect |
| --- | --- |
| Segment rules as data | ORIQ already keeps rules as data (catalog tests/limits, `QCRequirement`/`QCLimit`, `HoldingTimeRule`, `PreservationRule`, `Qualifier`, `ImportProfile`, report mappings) but hard-codes the environmental release gate and matrix choices. Replace `TestDefinition.matrix` choices and gate checks with a configurable **rule set** (per segment/product/site: required review steps, signature meanings, retest/expiry rules, limit types, report templates), selected per product/material or lot. Reuse the "rules as rows + versioned + audited" pattern; do not hard-code segment names in code. |
| Drop list revisited | Still drop NYSDEC EDD, MDL, quotes/price lists. Holding-time/preservation machinery is the closest analogue of configurable expiry/shelf-life/hold rules: keep as a **pattern** (rule rows evaluated at gate time, decisions with reason), rename and generalise rather than delete outright. |
| Catalog | Becomes the configuration hub: methods/specifications with versions, characteristic types, units, limit kinds (min/max/target/alert/action), Decimal precision, segment tags. Single owner, designed first. |
| Release gate | Generalise `analytical/services.py` and `reporting/services.py` release logic: keep lock + recheck + snapshot + hash mechanics; the checks list comes from the active rule set. Highest-risk edit; needs tests per segment profile (synthetic). |
| Audit trail | `core.AuditEvent` (actor, action, object, before/after JSON, reason, DB-immutable via trigger `core/migrations/0002_audit_immutable.py`) and `ResultRevision`/`CustodyEvent` histories are reusable core. Gaps vs Part 11 style audit: no session/IP, no field-level old/new standard, no mandatory-reason policy per action, no audit review report. Extend, do not replace; keep trigger approach. |
| Electronic signatures | **Not present in ORIQ** (no signature model; release uses `accounts.authorize_release` permission plus audited transition; allauth password/MFA only). New build: `ElectronicSignature` records (signer, meaning, timestamp, record ref, content hash/revision, PIN/credential re-entry verification) written in the same transaction as the state transition and AuditEvent, immutable by trigger. Reuse: release-permission concept, "nobody reviews own results", same-transaction transition pattern, `form_dialog` for a signing dialog (re-entry modal) and `history_item` for display. Signature PIN needs its own hashing (Django password hasher), lockout/rate-limit and policy; do not store PIN in clear. Needs a UI standard addition (signing dialog, signature manifestation on records and PDF reports). |
| Roles | `accounts/roles.py` mechanism stays; role set becomes configurable/per segment (QC analyst, reviewer, QA approver, supervisor, admin) plus signature meanings (authored, reviewed, approved). |
| Intake entity | Samples come from lots/batches/work orders, incoming material or stability pulls, not field COCs: replace Client/Project/Order with a generic lot/batch + product/material model; keep Sample/Container/CustodyEvent. |
| Reports | Versioned immutable PDF mechanics reused for CoA/test report and batch record; templates become configurable per segment. |
| Seed/test data | Synthetic profile per segment to prove configuration (one rule set each), replacing water/soil seed. |
| Compliance wording | Do not claim Part 11/cGMP/ISO compliance; say "supports" and state validation remains the deployer's job. |

Migration strategy (§5) unchanged except: add `signatures` (or extend `core`) and the rule-set models to stage (a)/(b) before analytical/reporting ports.

**Deployment update (user-authorized 2026-11-10, once an integrated build passes checks):** web `open-qual-iq`, plan `1c-2g`, virginia; Postgres `open-qual-iq-db`, plan `0.5c-1g`, 5 GB, PG 17. These equal ORIQ's plans, so `render.yaml` needs renames only (§6). The spending question in §6 and §8 is resolved; provisioning still waits for a passing integrated build.
