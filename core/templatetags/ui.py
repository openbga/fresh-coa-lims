"""Shared page components (docs/ui-standards.md): every one is a tag of this library.

  {% load ui %}
  {% status label="Quarantine" tone="hold" %}
  {% icon name="plus-lg" %}
  {% panel title="Receipt" %}
    {% fill actions %}<a class="btn btn-sm btn-outline-secondary" href="...">Edit</a>{% endfill %}
    ...body...
  {% endpanel %}
  {% fact label="Material" value=lot.material %}           one dt/dd row; without value= a block

COMPONENTS below is the one declaration: each tag's template under templates/includes/ (whose
header comment documents it), its keyword parameters, the page variables it is documented to read,
and whether it wraps a body. Every tag renders its template in a context of its own, built from:
  - its parameters: keyword arguments only; an unknown one is a template syntax error, and one the
    caller leaves out is empty ("", as a missing variable renders), never a page variable of the
    same name;
  - its documented reads (`reads`): page variables taken from the caller's context, each only when
    the caller does not pass it as a parameter;
  - request, user and csrf_token.
The output is stripped of surrounding whitespace. A block tag's body renders first, in the page's
context. {% fill name %} ... {% endfill %}, written directly inside the tag (not inside an
{% if %}), renders into the named part (slots.<name>) instead of the body. The body and each part
are stripped of surrounding whitespace, so an empty body is falsy.
tests/test_include_isolation.py renders every component with decoy page variables.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from django import template
from django.template.base import token_kwargs
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from core.grids import PageSizeForm
from core.navigation import nav_sections

register = template.Library()

# The one mapping from a status tone (includes/status.html) to a Bootstrap alert variant and the
# label a notice opens with when the caller gives none.
NOTICE_TONES = {
    "neutral": ("secondary", "Note"),
    "info": ("info", "Note"),
    "progress": ("progress", "In progress"),
    "success": ("success", "Done"),
    "warning": ("warning", "Warning"),
    "danger": ("danger", "Error"),
    "hold": ("hold", "On hold"),
}

# Page variables every component may read.
PASS_THROUGH = ("request", "user", "csrf_token")

# The sidebar's visibility flags (accounts.context_processors.account_navigation).
NAV_FLAGS = ("can_view_workspace", "can_view_audit", "can_manage_accounts")


class FillNode(template.Node):
    def __init__(self, name, nodelist):
        self.name, self.nodelist = name, nodelist

    def render(self, context):
        # A component collects its direct {% fill %} children; one reached here sits inside
        # another tag ({% if %}, {% for %}) and would vanish silently.
        raise template.TemplateSyntaxError(
            f"{{% fill {self.name} %}} must sit directly inside its component tag; "
            "put conditions inside the fill"
        )


@register.tag
def fill(parser, token):
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError(
            "{% fill %} takes one part name, e.g. {% fill actions %}"
        )
    nodelist = parser.parse(("endfill",))
    parser.delete_first_token()
    return FillNode(bits[1], nodelist)


@dataclass(frozen=True)
class Component:
    template: str
    params: tuple = ()
    reads: tuple = ()  # documented page variables, taken when not passed as a parameter
    body: str = ""  # "" no body; "block" always a block; "unless:<param>" a block unless given
    derive: Callable | None = None  # extra template values from (values, body, slots, has_body)
    caller_templates: tuple = ()  # parameters naming a template rendered in the page's context


class ComponentNode(template.Node):
    def __init__(self, name, spec, kwargs, nodelist):
        self.name, self.spec, self.kwargs, self.nodelist = name, spec, kwargs, nodelist

    def render(self, context):
        spec = self.spec
        values = dict.fromkeys(spec.params, "")
        for name in spec.reads:
            if name not in self.kwargs:
                values[name] = context.get(name, "")
        values.update({name: value.resolve(context) for name, value in self.kwargs.items()})
        engine = context.template.engine
        for name in spec.caller_templates:
            if values[name]:
                values[name] = mark_safe(engine.get_template(values[name]).render(context))
        body, slots = "", {}
        if self.nodelist is not None:
            parts = []
            for node in self.nodelist:
                if isinstance(node, FillNode):
                    slots[node.name] = mark_safe(node.nodelist.render(context).strip())
                else:
                    parts.append(node.render_annotated(context))
            body = mark_safe("".join(parts).strip())
        if spec.body:
            values["body"], values["slots"] = body, slots
        for name in PASS_THROUGH:
            values.setdefault(name, context.get(name, ""))
        if spec.derive:
            values.update(spec.derive(values, body, slots, self.nodelist is not None))
        # Stripped: an include's header comment and final newline would otherwise put stray
        # whitespace around inline components (an icon before a status label).
        return mark_safe(engine.get_template(spec.template).render(context.new(values)).strip())


def compile_component(name, spec):
    def compile_tag(parser, token):
        bits = token.split_contents()
        kwargs = token_kwargs(bits[1:], parser, support_legacy=False)
        if len(kwargs) != len(bits) - 1:
            raise template.TemplateSyntaxError(
                f"{{% {name} %}} takes keyword arguments only (name=value)"
            )
        unknown = set(kwargs) - set(spec.params)
        if unknown:
            raise template.TemplateSyntaxError(
                f"{{% {name} %}} has no parameter {', '.join(sorted(unknown))}"
            )
        nodelist = None
        unless = spec.body.removeprefix("unless:")
        if spec.body == "block" or (spec.body.startswith("unless:") and unless not in kwargs):
            nodelist = parser.parse((f"end{name}",))
            parser.delete_first_token()
        return ComponentNode(name, spec, kwargs, nodelist)

    return compile_tag


def heading_values(values, body, slots, has_body):
    title = values.get("title") or strip_tags(slots.get("title", "")) or "panel"
    return {"heading_id": values["heading_id"] or f"{slugify(title)}-heading"}


def list_results_values(values, body, slots, has_body):
    items = values["items"]
    paginator = getattr(items, "paginator", None)
    has_rows = bool(paginator.count) if paginator is not None else bool(items)
    return {
        "has_rows": has_rows,
        "paginated": paginator is not None and values["paginate"] is not False,
    }


def notice_values(values, body, slots, has_body):
    tone = values["tone"] or "info"
    if tone not in NOTICE_TONES:
        raise template.TemplateSyntaxError(
            f"{{% notice %}} tone must be one of {', '.join(NOTICE_TONES)}"
        )
    variant, label = NOTICE_TONES[tone]
    return {"tone": tone, "variant": variant, "label": values["label"] or label}


def history_panel_values(values, body, slots, has_body):
    title = values["title"] or "History"
    events = values["events"] or []
    if values["newest_first"]:
        events = list(reversed(list(events)))
    return {
        "title": title,
        "events": events,
        "heading_id": values["heading_id"] or f"{slugify(title)}-heading",
    }


# The one Bootstrap Icons glyph per status tone (includes/status.html).
STATUS_GLYPHS = {
    "neutral": "circle",
    "info": "circle-fill",
    "progress": "circle-half",
    "success": "check-circle-fill",
    "warning": "exclamation-triangle-fill",
    "danger": "x-circle-fill",
    "hold": "pause-circle-fill",
}


def status_values(values, body, slots, has_body):
    tone = values["tone"] if values["tone"] in STATUS_GLYPHS else "neutral"
    return {"tone": tone, "glyph": "" if values["print"] else STATUS_GLYPHS[tone]}


def empty_state_values(values, body, slots, has_body):
    kind = values["kind"] or "empty"
    return {"kind": kind, "glyph": EMPTY_GLYPHS.get(kind, "inbox")}


EMPTY_GLYPHS = {"empty": "inbox", "no-results": "funnel", "error": "x-circle-fill"}


def form_actions_values(values, body, slots, has_body):
    return {"extra": body}


def fact_values(values, body, slots, has_body):
    value = body if has_body else values["value"]
    blank = value is None or (isinstance(value, str) and not value.strip())
    critical = values["critical"]
    if critical and critical not in STATUS_GLYPHS:
        raise template.TemplateSyntaxError(
            f"{{% fact %}} critical must be one of {', '.join(STATUS_GLYPHS)}"
        )
    return {
        "value": None if blank else value,
        "critical_glyph": STATUS_GLYPHS.get(critical, "") if critical else "",
    }


# Material kinds (catalog.models.MaterialKind) → the tag's data-kind and Bootstrap icon.
MATERIAL_KINDS = {
    "raw_material": ("raw", "basket2"),
    "component": ("component", "gear"),
    "packaging": ("packaging", "box2"),
    "intermediate": ("intermediate", "layers-half"),
    "finished_product": ("finished", "bag-check"),
}


def material_tag_values(values, body, slots, has_body):
    material = values["material"]
    if hasattr(material, "kind"):  # a catalog Material
        name, kind, code = material.name, material.kind, material.code
    else:  # the material as text (a lot's), with its kind and code when known
        name, kind, code = str(material or ""), values["kind"], values["code"]
    data_kind, icon = MATERIAL_KINDS.get(kind, ("", "box-seam"))
    sub = values["sub"]
    sub = "" if sub is False else (sub or code or "")
    return {"name": name, "data_kind": data_kind, "glyph": icon, "sub": sub}


def code_values(values, body, slots, has_body):
    value = str(values["value"] if values["value"] is not None else "")
    if values["hash"]:
        return {"shown": value[:12], "full": value}
    return {"shown": value, "full": values["title"] or ""}


ISO_MOMENT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def humanize_key(key):
    text = str(key).replace("_", " ").strip()
    return text[:1].upper() + text[1:]


def value_items(data, exclude=()):
    """(label, kind, value) rows of a mapping for includes/value_list.html; never a repr."""
    rows = []
    items = data.items() if isinstance(data, dict) else enumerate(data or [])
    for key, value in items:
        if key in exclude:
            continue
        label = humanize_key(key) if isinstance(data, dict) else ""
        if value is None or value == "" or value == [] or value == {}:
            rows.append((label, "empty", None))
        elif isinstance(value, bool):
            rows.append((label, "text", "Yes" if value else "No"))
        elif isinstance(value, dict):
            rows.append((label, "dict", value))
        elif isinstance(value, list) and all(isinstance(v, str | int) for v in value):
            rows.append((label, "codes", value))
        elif isinstance(value, list):
            rows.append((label, "dict", dict(enumerate(value, start=1))))
        elif isinstance(value, str) and ISO_MOMENT.match(value):
            rows.append((label, "moment", value))
        else:
            rows.append((label, "text", value))
    return rows


def value_list_values(values, body, slots, has_body):
    exclude = tuple(k.strip() for k in str(values["exclude"] or "").split(",") if k.strip())
    data = values["data"]
    return {"rows": value_items(data, exclude) if isinstance(data, dict | list) else []}


def nav_values(values, body, slots, has_body):
    user = values["user"]
    flags = {name: values[name] for name in NAV_FLAGS}
    flags["is_authenticated"] = bool(getattr(user, "is_authenticated", False))
    request = values["request"]
    return {"sections": nav_sections(request, flags) if request else []}


I = "includes/"  # noqa: E741
COMPONENTS = {
    # Wrapping components (block tags)
    "panel": Component(
        I + "panel.html",
        ("title", "heading_id", "count", "table", "flush", "hidden_title", "collapsible",
         "open", "class", "id", "body_class", "hook"),
        body="block",
        derive=heading_values,
    ),
    "signature_card": Component(
        I + "signature_card.html", ("title", "heading_id", "hook", "class"), body="block"
    ),
    "panel_section": Component(I + "panel_section.html", ("rule", "class"), body="block"),
    "list_results": Component(
        I + "list_results.html",
        ("items", "noun", "filtered", "invalid", "clear_url", "paginate", "sizes",
         "empty_title", "empty_body", "action_url", "action_label", "no_results_title",
         "no_results_body", "error_body"),
        body="block",
        derive=list_results_values,
    ),
    "notice": Component(
        I + "notice.html",
        ("tone", "label", "heading", "blocking", "dismissible", "focus", "hidden", "id",
         "class", "hook"),
        body="block",
        derive=notice_values,
    ),
    "form_page": Component(
        I + "form_page.html",
        ("form", "formset", "formset_label", "action", "multipart", "note", "times",
         "no_required_note", "cancel_url", "cancel_label", "cancel_hook", "submit_label",
         "destructive", "secondary", "no_submit", "method", "id", "class", "autocomplete_off",
         "hook", "submit_icon"),
        body="block",
    ),
    "form_actions": Component(
        I + "form_actions.html",
        ("cancel_url", "cancel_label", "cancel_hook", "submit_label", "destructive", "secondary",
         "no_submit", "name", "value", "submit_icon"),
        body="block",
        derive=form_actions_values,
    ),
    "history_panel": Component(
        I + "history_panel.html",
        ("events", "newest_first", "title", "heading_id", "count", "class", "empty_title",
         "empty_body"),
        body="block",
        reads=("form_dialog",),
        derive=history_panel_values,
    ),
    "page_meta": Component(I + "page_meta.html", body="block"),
    "more_actions": Component(I + "more_actions.html", ("label",), body="block"),
    "record_layout": Component(I + "record_layout.html", ("aside_label",), body="block"),
    "fact": Component(
        I + "fact.html",
        ("label", "value", "empty", "class", "wide", "truncate", "critical"),
        body="unless:value",
        derive=fact_values,
    ),
    # Single components
    "icon": Component(I + "icon.html", ("name", "class")),
    "status": Component(
        I + "status.html", ("label", "tone", "plain", "title", "print"), derive=status_values
    ),
    "brand": Component(I + "brand.html", ("href", "name", "compact", "variant")),
    "breadcrumbs": Component(
        I + "breadcrumbs.html",
        ("crumbs", "section", "section_url", "tab", "tab_url", "record", "record_url", "child",
         "child_url", "current"),
        reads=("page_title",),
    ),
    "confirm_dialog": Component(
        I + "confirm_dialog.html",
        ("id", "label", "object", "title", "body", "action", "hidden_name", "hidden_value",
         "confirm_hook", "cancel_hook", "cancel_label"),
    ),
    "empty_state": Component(
        I + "empty_state.html",
        ("kind", "title", "body", "action_url", "action_label", "clear_url"),
        derive=empty_state_values,
    ),
    "filter_chips": Component(I + "filter_chips.html", ("chips",)),
    "form_errors": Component(I + "form_errors.html", ("form", "formset", "formset_label")),
    "required_note": Component(I + "required_note.html", ("note", "times")),
    "field": Component(I + "field.html", ("field", "prefix", "suffix", "no_help", "label")),
    "grid_search": Component(
        I + "grid_search.html", ("value", "placeholder", "label", "name", "id")
    ),
    "grid_toolbar": Component(
        I + "grid_toolbar.html",
        ("label", "q", "placeholder", "search_label", "search_id", "no_search", "inline",
         "more", "more_open", "active", "clear_url", "grid", "hidden", "invalid", "chips",
         "sort", "submit_label", "note", "extra_name", "extra_value", "extra_label"),
    ),
    "grid_columns_button": Component(I + "grid_columns_button.html", ("grid",)),
    "sort_header": Component(
        I + "sort_header.html",
        ("label", "asc", "desc", "first", "sort", "class", "col", "locked", "hidden", "priority"),
    ),
    "pagination": Component(
        I + "pagination.html", ("page_obj", "noun", "filtered", "sizes"),
    ),
    "select_all": Component(I + "select_all.html", ("name", "label", "ready_label")),
    "row_select": Component(
        I + "row_select.html",
        ("name", "value", "label", "form_id", "ready", "checked", "disabled", "id",
         "describedby"),
    ),
    "post_button": Component(
        I + "post_button.html",
        ("action", "label", "variant", "small", "fields", "name", "value", "icon", "id"),
    ),
    "history_item": Component(
        I + "history_item.html",
        ("title", "at", "actor", "by", "reason", "changes", "detail", "extra", "icon"),
        caller_templates=("extra",),
    ),
    "signature_list": Component(
        I + "signature_list.html", ("signatures", "subject", "numbered", "empty", "hash")
    ),
    "kind_tag": Component(I + "kind_tag.html", ("label",)),
    "material_tag": Component(
        I + "material_tag.html",
        ("material", "kind", "code", "size", "sub"),
        derive=material_tag_values,
    ),
    "code": Component(I + "code.html", ("value", "href", "title", "hash"), derive=code_values),
    "value_list": Component(
        I + "value_list.html", ("data", "compact", "nested", "exclude"), derive=value_list_values
    ),
    "route": Component(I + "route.html", ("stages", "label", "micro", "summary")),
    "page_toc": Component(I + "page_toc.html", ("items", "label")),
    "record_foot": Component(I + "record_foot.html", ("identifier",)),
    "app_footer": Component(I + "app_footer.html", ("centered",), reads=("source_code_url",)),
    "section_tabs": Component(I + "section_tabs.html", ("tabs", "label")),
    "nav": Component(I + "nav.html", reads=NAV_FLAGS, derive=nav_values),
    "dateline": Component(I + "dateline.html"),
    "messages": Component(I + "messages.html", reads=("messages",)),
    "theme_menu": Component(I + "theme_menu.html"),
    "form_dialog": Component(I + "form_dialog.html"),
}  # fmt: skip

for _name, _spec in COMPONENTS.items():
    register.tag(_name, compile_component(_name, _spec))


@register.simple_tag
def page_size_field(per_page, noun):
    """The rows-per-page select of includes/pagination.html, as a bound form field.

    {% page_size_field paginator.per_page noun as field %}{{ field }}  (id "per-page-<noun>")
    """
    form = PageSizeForm(initial={"per_page": per_page})
    widget = form.fields["per_page"].widget
    widget.attrs.update(
        {
            "id": f"per-page-{slugify(noun or 'records')}",
            "class": "form-select form-select-sm w-auto",
            "data-vr-autosubmit": "",  # app.js submits on change; Show stays for no-JS
        }
    )
    return form["per_page"]


@register.filter
def action_label(code):
    """An audit action code in words for a history entry ("test.assigned" → "Test assigned").

    Display only: the audit trail, its CSV export and recorded evidence keep the raw code.
    """
    text = str(code or "").replace(".", " ").replace("_", " ").strip()
    return text[:1].upper() + text[1:]


@register.filter
def when(value, style=""):
    """A moment as the app shows it everywhere, inside <time datetime="ISO">: "2026-11-17 09:54
    UTC" (Y-m-d H:i T, laboratory time zone), |when:"date" → "2026-11-17", |when:"seconds" →
    seconds as in signatures and the audit trail. Takes a datetime, a date or an ISO string
    (frozen JSON); never microseconds or "+00:00". Empty → "—"."""
    from datetime import date, datetime

    from django.utils import timezone
    from django.utils.dateformat import format as date_format
    from django.utils.html import format_html

    if value in (None, ""):
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        if style == "date":
            return format_html(
                '<time datetime="{}">{}</time>',
                value.date().isoformat(),
                date_format(value, "Y-m-d"),
            )
        shown = date_format(value, "Y-m-d H:i:s T" if style == "seconds" else "Y-m-d H:i T")
        return format_html('<time datetime="{}">{}</time>', value.isoformat(), shown)
    if isinstance(value, date):
        return format_html('<time datetime="{0}">{0}</time>', value.isoformat())
    return value
