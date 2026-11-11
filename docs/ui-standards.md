# UI standards

Baseline: 2026-11-10. These are the OpenBGA Qual house rules. The shared templates and `static/css/app.css` are the implementation reference. The foundation establishes the shell; later modules must complete these states rather than treating this document as a claim that every component already exists.

## Components and theme

The product name is **OpenBGA Qual** throughout the application shell, sign-in page, browser titles, documentation and newly issued certificates. Existing issued PDF bytes retain their original branding. The repository is [openbga/qual](https://github.com/openbga/qual).

Bootstrap is the component library. Use the inherited `--vr-*` tokens mapped to Bootstrap variables; the retained prefix is a compatibility choice, not product branding. Use the local pinned assets and retained vendor notices. New pages must not invent a second control, dialog or table framework. No template-specific colours, inline styles or utilities that bypass light/dark theme tokens. Print uses a legible light theme.

| Page type | Header and navigation | Main content |
|---|---|---|
| List | Sidebar label is page title; one `New <thing>` action | Search/filter toolbar, authorized server-side sorting/paging, table and count |
| Record | Breadcrumbs, record ID, textual status, key facts and next action | Related evidence, observations, history and signature manifestations |
| Form/action | Same action wording as opener; full-page fallback | Labelled groups, explicit units, inline errors and submit/cancel row |
| Entry grid | Wide accessible form, clear sample/test identity | Exact values, units/limits, validation by row, sticky actions when useful |
| Overview | Work queues linking to filtered lists | Actionable counts and clear empty states |
| Document | Breadcrumbs and version identity | Preview of issued content, download/version/amendment controls |

One destination has one navigation home. Mark exactly one current sidebar item on its lists, records and actions; account pages may mark none. Breadcrumbs belong on record/action/document pages, not lists. Cross-links belong beside the evidence they reference. Reuse shared includes before copying markup. Use the OpenBGA Qual name and mark throughout, with manufacturing QC imagery and terms.

Sibling list and overview pages put section navigation above the page header, in one consistent
position independent of title length, descriptions, datelines, messages or available actions.
Keep those links on one horizontally scrollable row when space is limited, including beside
the documentation panel. The current link stays visible and its emphasis must not change link
widths. Use page links with `aria-current`, not widget tabs for full-page navigation. Align page
actions with the heading and place supporting descriptions below that row; allow long text and
controls to wrap without clipping. List filters share field widths, labelled controls and a
wrapping action group, with one field per row on phones.

Every page ends with the shared application footer (`includes/app_footer.html`): product name, licence and the **Source code** link required by AGPL-3.0 section 13. It sits outside `<main>`, so form dialogs never copy it.

## Lists and forms

Tables expose identity first, status nearby, numbers aligned with units in headings, unambiguous dates and actions last. The server filters, sorts and paginates the entire authorized queryset. DataTables, when used, only manages column presentation. Filters preserve input and have an explicit clear action. Show empty, filtered-empty, denied, failed and successful states with useful next actions; never show a blank table as the only explanation.

Forms use Django validation with escaped values and CSRF. Preserve nonsecret input after errors; never repopulate a PIN. Labels are visible and associated with controls. Required status, format and units are explicit. Link error summaries to fields; do not rely on colour alone. Full-page forms remain usable without JavaScript. HTMX responses preserve focus and messages, and must not hide server errors. Use the shared form dialog where it is supported; do not build separate modal infrastructure for each module.

## Signing and review

| Element | Required behavior |
|---|---|
| Context | Show record ID and exact revision, proposed transition and human-readable signing meaning |
| Identity | Show the current individual signer; changing identity requires a new authenticated session |
| Credential | Label `Signature PIN`; masked entry, numeric input hint, no stored/autofilled value in page markup |
| Consent | Explicit `Sign and review` / `Sign and approve` / `Sign disposition` action; opening a dialog never signs |
| Reason | Capture the transition reason when required; distinguish review comments from credential input |
| Failure | Preserve safe input, clear PIN, explain invalid credential, lockout or stale revision without silently retrying |
| Keyboard | Focus enters the dialog, stays within it, and returns to the opener; Escape/Cancel has no mutation |
| Manifestation | Display signer, meaning, timestamp and bound revision beside the signed record/history |

Before rendering an action or signing form, check the role, state, authorship and prerequisites already known on GET. Explain an unavailable action and return to its record or review page before requesting a PIN. Reuse domain predicates without mutating evidence; the submitted action must still revalidate current authority and state under its transaction locks.

The signing component is a view of a server-enforced transition. Never offer self-review or suggest that an administrator can bypass independence. A record changed since the dialog opened must require renewed review and PIN entry. Audit review shows actor, action, old/new values, reason and timestamp; distinguish inspecting history from formally recording a review. PINs and hashes never appear in history or exports.

## Language and accessibility

Use sentence case and one term per concept. `New <thing>` creates, `Record` adds an observation, `Change` changes a controlled state, `Correct` preserves a prior record with a reason, and `Cancel` exits without saving. State what a decision means: `QC disposition` does not mean manufacturer release. Describe compliance-supporting controls without claiming certification.

Use semantic headings, real buttons for actions and links for navigation. Provide visible focus, sufficient contrast in both themes, text with status colour, labelled icon-only controls and accessible modal behavior. Keep dense tables readable at normal zoom; allow horizontal table scrolling instead of clipping data. Test the real journey at desktop and narrow widths, with keyboard navigation, validation errors, denied permissions and a failed signing attempt.

Page documentation uses the shared `pagedocs` right-side panel, accessed at the top-right of the top bar. Keep field help on forms and page-level explanations in `docs/pages/`; avoid separate per-page help modals. The panel follows navigation and remembers open state and width.

On phone widths, the top bar shows Menu as a labelled icon, reserves room for theme, sign-out and page-documentation controls, and truncates only the brand text if needed. Verify the shell in Linux Chromium as well as the local browser: system-font metrics must not push controls outside the viewport. Do not mask layout overflow with page-wide clipping.
