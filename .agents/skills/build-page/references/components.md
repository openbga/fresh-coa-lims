# Components, controls and list columns

The source of truth is each `templates/includes/<name>.html` header comment and the `COMPONENTS`
registry in `core/templatetags/ui.py`. This table is the map; read the header before using a tag.
Every tag takes keyword arguments only; an unknown one is a `TemplateSyntaxError`, an omitted one
is empty and is never read from the page. `{% fill part %}…{% endfill %}` fills a named part of a
block tag (directly inside it, not inside an `{% if %}`).

## Block tags

| Tag | Use | Parts / key parameters |
| --- | --- | --- |
| `panel` … `endpanel` | Every card | parts title, actions, count, footer; `table=True` flush table card, `hidden_title` for a list's single card, `collapsible`, `open` |
| `panel_section` | Stacked bodies in `panel flush=True` | `rule` |
| `list_results` | A list's table with pagination, empty, no-results and filter-error states | `items` (a Page), `noun`, `filtered`, `invalid`, `clear_url`, `sizes` (only with `core.grids.paginate`), `empty_*`, `no_results_*`, `action_url/label` |
| `notice` | Every alert | `tone` neutral/info/progress/success/warning/danger/hold, `blocking` (role=alert), `dismissible`, `label`, `heading` |
| `form_page` | Every form page | `form`, `formset`, `cancel_url`, `submit_label`, `submit_icon`, `destructive`, `secondary`, `multipart`; parts note, actions. Never `{{ form }}` in the body |
| `form_actions` | Action row | destructive first, Cancel link, primary last; `name`/`value` for multi-action forms |
| `signature_card` | Every sign page | part summary; body = the sign form or the refusal; `hook="signature-dialog"` when signing is allowed |
| `history_panel` | Audit history, last on a record | `events` (AuditEvents) or a body of `history_item`s |
| `page_meta` | Header facts | status first, at most four `<li>` |
| `more_actions` | Header "More" menu | destructive item: `a.dropdown-item.vr-menu-danger` |
| `record_layout` | Record lead panel and aside | fills lead, aside |
| `fact` | One `dt`/`dd` in `dl.vr-facts` | `label`, `value` or a block body, `empty`, `wide` |

## Single tags

| Tag | Use |
| --- | --- |
| `icon name=` | Bootstrap Icons sprite symbol (decorative; pair with text) |
| `status label= tone= plain= title= print=` | Text + tone glyph; `print=True` for WeasyPrint documents (no glyph) |
| `breadcrumbs …` | Record, form, action and document pages only |
| `section_tabs tabs=` | Full-page sibling navigation (links with `aria-current`) |
| `grid_toolbar …` | The one GET list toolbar: search, inline filter fields, More filters, Apply, Clear all, Columns, chips |
| `grid_search`, `grid_columns_button`, `filter_chips` | Toolbar pieces |
| `sort_header label= asc= desc= col= locked= hidden= priority=` | A sortable `<th>`; pass `desc` explicitly |
| `pagination page_obj= noun= sizes=` | Count, rows per page, first/prev/next/last |
| `empty_state kind=` | empty / no-results / error (inside `list_results` already) |
| `select_all`, `row_select` | Bulk selection |
| `post_button action= label=` | One-button POST (button-only state change) |
| `confirm_dialog …` | Yes/no modal for one irreversible POST without inputs |
| `history_item title= at= actor= reason= changes= icon=` | One timeline entry; `changes` = (label, before, after) |
| `signature_list signatures= subject= numbered= hash=` | Signature manifestations with `data-signature-meaning` / `data-signature-revision` hooks |
| `form_errors`, `required_note`, `field field= prefix= suffix=` | Form pieces |
| `page_toc items=` | "On this page" for long pages |
| `record_foot identifier=` | In `{% block record_foot %}` on record pages |
| `kind_tag label=` | Test kind after the test name (Retest, Resample, …) |
| `route stages=` | The six-step QC route (`quality/route.py` builds the stages) |
| `brand`, `app_footer`, `theme_menu`, `dateline`, `messages`, `nav`, `form_dialog` | Shell pieces (the layout renders them; `form_dialog` is the shared form dialog that `core/form_surfaces.py` routes open in) |

Shell blocks (`templates/layouts/document.html`): `page_title` comes from the view; `breadcrumbs`,
`page_meta`, `page_actions` (≤3 secondaries, `more_actions`, the primary last), `page_intro`,
`content`, `record_foot`, `page_title_class` (`" vr-data"` when the title is an identifier).

## Form controls

| Need | Field / widget | Rendered by |
| --- | --- | --- |
| Choice (short list) | `ChoiceField` / `ModelChoiceField` | `widgets/select.html` → Tom Select (search above eight options) |
| Large or growing model list | `ModelChoiceField(widget=core.lookups.RemoteSelect("<lookup>"))`, `RemoteSelectMultiple` | `select.html` + `data-vr-lookup`, options from `core:lookup` |
| Date / date-time | `DateInput` / `DateTimeInput` | `widgets/date.html` → typed field + calendar popover in the lab time zone |
| Exact number | `DecimalField` with `NumberInput(attrs={"unit": "mg/g"})` | `widgets/number.html` → text input, unit addon, no spinner |
| File | `FileField` | `widgets/file.html` / `clearable_file_input.html` → drop zone |
| Text | `CharField` / `Textarea` | `widgets/input.html` / `textarea.html` |
| Checkbox / radio lists | `CheckboxSelectMultiple` / `RadioSelect` | `widgets/multiple_input.html` |
| PIN | `PasswordInput`, never prefilled | the signature component |

## List columns

| Need | How |
| --- | --- |
| Server paging, size choice | `core.grids.paginate(request, qs)`; `{% list_results sizes=True %}` |
| Sort | `{% sort_header asc="number" desc="-number" sort=sort %}`; the view orders the queryset |
| Show, hide, reorder | `<table data-vr-grid="<app>.<list>" data-vr-grid-version="1">` + `{% grid_columns_button grid=… %}` |
| Column identity | `col="<id>"` (stable; renaming bumps the grid version), `locked=True` for the identifier and actions |
| Default hidden below 1366px | `priority="low"` |
| Saved per user | `core/preferences.py` (`grid:<grid>:v<n>`, `page:<view name>`), through `window.vrPreferences` |
