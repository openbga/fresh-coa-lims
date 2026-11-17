"""Shared components read only what their caller passes (docs/ui-standards.md).

A Django {% include %} sees its caller's whole context, so an optional parameter the caller left
out was silently filled by any page variable of the same name: a page's `form` once became a
checkbox's form attribute. Every shared component is therefore a `ui` tag
(core/templatetags/ui.py) that renders in a context of its own: its keyword parameters (an omitted
one is empty, never a page variable), its documented reads (breadcrumbs' page_title, app_footer's
source_code_url, messages' messages, nav's account flags), and request, user and csrf_token.

Every component of the registry has a case (test_every_component_has_a_case). Each is rendered
with only its explicit arguments, once in a clean context and once with a decoy page variable for
each generic name pages use; the two renderings must be identical. KNOWN_LEAKS stays empty: a
component that starts reading a page variable fails here.
"""

import re

import pytest
from django.template import Context, Template

DECOY_NAMES = [
    "form", "formset", "formset_label", "class", "css", "title", "heading", "heading_id", "items",
    "label", "name", "value", "id", "note", "times", "icon", "small", "checked", "disabled",
    "ready", "describedby", "form_id", "action", "fields", "variant", "field", "body", "kind",
    "tone", "plain", "count", "url", "href", "hidden", "focus", "dismissible", "blocking", "empty",
    "record", "record_url", "current", "section", "section_url", "tab", "tab_url", "crumbs",
    "cancel_url", "submit_label", "destructive", "secondary", "no_submit", "extra", "multipart",
    "object", "hidden_name", "hidden_value", "chips", "grid", "invalid", "clear_url",
    "action_url", "action_label", "noun", "filtered", "post_name", "paginate", "actor", "at",
    "by", "reason", "changes", "detail", "rule", "table", "flush", "collapsible", "body_class",
    "events", "newest_first", "empty_title", "empty_body", "placeholder", "search_id", "prefix",
    "suffix", "ready_label", "identifier", "portal", "hook", "slots", "q", "sort", "page_obj",
    "sizes", "subject", "numbered", "hash", "signatures", "centered", "compact", "tabs",
    "aside_label", "inline", "more", "active", "cancel_label", "autocomplete_off",
    "search_label", "sections", "lot", "results",
]  # fmt: skip


def rendered(template, context):
    """The output with the time of rendering ({% now %} in record_foot) masked."""
    return re.sub(r'datetime="[^"]*"', 'datetime="now"', template.render(context))


def page_context(request, values):
    """The page's context as an include sees it ({% querystring %} reads context.request)."""
    context = Context(values)
    context.request = request
    return context


class Decoy:
    """A page variable of any shape: truthy, printable, iterable, with every attribute."""

    def __str__(self):
        return "DECOY"

    __html__ = __str__

    def __bool__(self):
        return True

    def __len__(self):
        return 1

    def __iter__(self):
        return iter([self])

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __getitem__(self, key):
        return self

    def __call__(self, *args, **kwargs):
        return self


# Each component with the arguments a typical caller passes explicitly.
CASES = {
    "app_footer": "{% load ui %}{% app_footer %}",
    "brand": '{% load ui %}{% brand href="/" %}',
    "breadcrumbs": '{% load ui %}{% breadcrumbs section="Lots" section_url="/" current="L-1" %}',
    "confirm_dialog": '{% load ui %}{% confirm_dialog id="d" label="Withdraw certificate" '
    'body="Withdrawing is final." action="/withdraw/" %}',
    "dateline": "{% load ui %}{% dateline %}",
    "empty_state": '{% load ui %}{% empty_state kind="empty" title="Nothing yet" %}',
    "fact": '{% load ui %}<dl>{% fact label="Material" value="Lactose" %}</dl>',
    "field": "{% load ui %}{% field field=real_form.material %}",
    "filter_chips": "{% load ui %}{% filter_chips chips=no_chips %}",
    "form_actions": '{% load ui %}{% form_actions submit_label="Save" %}{% endform_actions %}',
    "form_errors": "{% load ui %}{% form_errors form=real_form %}",
    "form_dialog": "{% load ui %}{% form_dialog %}",
    "form_page": '{% load ui %}{% form_page form=real_form submit_label="Save" %}'
    "{% endform_page %}",
    "grid_columns_button": '{% load ui %}{% grid_columns_button grid="quality.lots" %}',
    "grid_search": '{% load ui %}{% grid_search value="" %}',
    "grid_toolbar": '{% load ui %}{% grid_toolbar label="Filter lots" inline=real_form %}',
    "history_item": '{% load ui %}{% history_item title="Received" at=when %}',
    "history_panel": "{% load ui %}{% history_panel events=no_events %}{% endhistory_panel %}",
    "icon": '{% load ui %}{% icon name="x" %}',
    "kind_tag": '{% load ui %}{% kind_tag label="Retest" %}',
    "list_results": '{% load ui %}{% list_results items=no_events noun="lots" %}'
    "<table></table>{% endlist_results %}",
    "messages": "{% load ui %}{% messages %}",
    "more_actions": "{% load ui %}{% more_actions %}<li>One</li>{% endmore_actions %}",
    "nav": "{% load ui %}{% nav %}",
    "notice": '{% load ui %}{% notice tone="warning" %}Check this.{% endnotice %}',
    "page_meta": "{% load ui %}{% page_meta %}<li>One</li>{% endpage_meta %}",
    "page_toc": "{% load ui %}{% page_toc items=toc %}",
    "pagination": '{% load ui %}{% pagination page_obj=one_page noun="lots" %}',
    "panel": '{% load ui %}{% panel title="Receipt" %}Body{% endpanel %}',
    "panel_section": "{% load ui %}{% panel_section %}Body{% endpanel_section %}",
    "post_button": '{% load ui %}{% post_button action="/go/" label="Issue" %}',
    "record_foot": '{% load ui %}{% record_foot identifier="L-1" %}',
    "record_layout": '{% load ui %}{% record_layout aside_label="Next" %}{% fill lead %}Lead'
    "{% endfill %}Rest{% endrecord_layout %}",
    "required_note": "{% load ui %}{% required_note %}",
    "route": "{% load ui %}{% route stages=no_events %}",
    "row_select": '{% load ui %}{% row_select name="events" value=1 %}',
    "section_tabs": "{% load ui %}{% section_tabs tabs=no_events %}",
    "select_all": '{% load ui %}{% select_all name="events" label="All" %}',
    "signature_card": '{% load ui %}{% signature_card title="Sign" %}Form{% endsignature_card %}',
    "signature_list": "{% load ui %}{% signature_list signatures=no_events %}",
    "sort_header": '{% load ui %}{% sort_header label="Lot" asc="number" '
    'desc="-number" sort="number" %}',
    "status": '{% load ui %}{% status label="Released" tone="success" %}',
    "theme_menu": "{% load ui %}{% theme_menu %}",
}


# Names each include still takes from the page when the caller omits them. Delete as fixed.
KNOWN_LEAKS = {}


def leaks(template, request, given):
    """Decoy names that change the output (or break it) when present in the page's context."""
    clean = rendered(template, page_context(request, given))
    found = set()
    for name in DECOY_NAMES:
        try:
            if rendered(template, page_context(request, {name: Decoy(), **given})) != clean:
                found.add(name)
        except Exception:  # a decoy the include cannot even render is a leak too
            found.add(name)
    return found


@pytest.mark.parametrize("case", sorted(CASES))
def test_include_ignores_page_variables_it_was_not_given(case, rf, django_user_model):
    from datetime import UTC, datetime

    from django import forms

    class RealForm(forms.Form):
        material = forms.CharField(required=False)

    from django.core.paginator import Paginator

    request = rf.get("/lots/")
    request.user = django_user_model(username="isolation", first_name="Test", last_name="Analyst")
    given = {
        "request": request,
        "user": request.user,
        "real_form": RealForm(),
        "no_chips": [],
        "no_events": [],
        "toc": [("samples", "Samples")],
        "one_page": Paginator(["L-1"], 25).page(1),
        "when": datetime(2026, 11, 9, 14, 5, tzinfo=UTC),
    }
    found = leaks(Template(CASES[case]), request, given)
    known = KNOWN_LEAKS.get(case, set())
    assert not found - known, f"{case} reads page variables not given: {sorted(found - known)}"
    assert not known - found, f"{case} no longer leaks {sorted(known - found)}: update KNOWN_LEAKS"


def test_decoy_names_are_unique():
    assert len(DECOY_NAMES) == len(set(DECOY_NAMES))


def test_every_component_has_a_case():
    from core.templatetags.ui import COMPONENTS

    assert set(CASES) == set(COMPONENTS)
