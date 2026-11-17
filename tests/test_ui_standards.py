"""Retired UI patterns (docs/ui-standards.md, "Enforced rules").

Each rule is a regular expression run over every first-party template with its comments removed;
a rule names the shared component (core/templatetags/ui.py, templates/includes/) that owns the
pattern instead. Rules in PENDING are switched on area by area as pages move onto the components:
until then they run as expected failures, and the failure message lists the templates left.
Remove a rule from PENDING once its list is empty; from then on it guards every template.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings

from core.templatetags.ui import COMPONENTS

ROOT = Path(settings.BASE_DIR)

# Documents rendered to PDF carry their own stylesheet and markup; they are not workspace pages.
DOCUMENTS = (
    "reporting/templates/reporting/pdf/",
    "reporting/templates/reporting/_certificate.html",  # screen preview and PDF share it
)
# The components themselves, and the Django widget templates (controls).
COMPONENT_DIRS = ("templates/includes/", "templates/django/forms/")
# Pages outside the staff shell: the sign-in pages and error pages draw their own heading.
STANDALONE = (
    "templates/registration/",
    "templates/403.html",
    "templates/404.html",
    "templates/413.html",
    "templates/500.html",
)

# Muted text is .vr-muted. Bootstrap colour utilities that app.css does not map onto the tokens
# (or that duplicate .vr-muted) are retired; the semantic ones (text-danger, btn-danger,
# alert-*, table-danger...) follow the status tones and stay allowed.
UNTHEMED_UTILITY = re.compile(
    r"""(?<=[\s"'])(?:text-(?:muted|body-secondary|body-tertiary|light|dark|white|black)"""
    r"""|bg-(?:white|light|dark|black|body|body-secondary|body-tertiary)"""
    r"""|text-bg-(?:light|dark)|border-(?:light|dark|white|black)|link-(?:light|dark)"""
    r"""|btn-(?:light|dark)|btn-outline-(?:light|dark)|table-(?:light|dark))(?=[\s"'])"""
)


def page_actions(source):
    return "".join(re.findall(r"{% block page_actions %}(.*?){% endblock", source, re.S))


PRIMARY_POST_BUTTON = re.compile(r"""{%\s*post_button\b[^%]*\bvariant=["']primary["']""")


def primaries(text):
    """Primary buttons written out, and post_button tags that render one."""
    return text.count("btn-primary") + len(PRIMARY_POST_BUTTON.findall(text))


def most_primaries(source):
    """Primary count on the fullest path through {% if %} branches (they exclude each other)."""
    stack, pos = [[0]], 0
    for tag in re.finditer(r"{%\s*(if|elif|else|endif)\b.*?%}", source):
        stack[-1][-1] += primaries(source[pos : tag.start()])
        pos = tag.end()
        if tag.group(1) == "if":
            stack.append([0])
        elif tag.group(1) == "endif" and len(stack) > 1:
            branches = stack.pop()
            stack[-1][-1] += max(branches)
        elif tag.group(1) != "endif":
            stack[-1].append(0)
    stack[-1][-1] += primaries(source[pos:])
    return sum(sum(level) for level in stack)


def own_h1(source):
    """A shell page that writes its own <h1> instead of setting page_title."""
    return '{% extends "base.html" %}' in source and bool(re.search(r"<h1\b", source))


def suppressed_header(source):
    return bool(re.search(r"{%\s*block page_header\s*%}\s*{%\s*endblock", source))


def too_many_primaries(source):
    return most_primaries(page_actions(source)) > 1


# name: (what the standard asks instead, pattern or predicate, templates exempt besides
# DOCUMENTS: owners of the pattern; entries ending in "/" are folders)
RULES = {
    "inline-style": (
        "No inline style attribute or <style> element (CSP style-src 'self'): use app.css classes",
        re.compile(r"""\sstyle\s*=|<style\b"""),
        (),
    ),
    "colour-literal": (
        "No colour literals in templates: use the --vr-* tokens through app.css",
        re.compile(
            r"""(?:fill|stroke|color|bgcolor)\s*=\s*["']?\s*#[0-9a-fA-F]{3,8}\b"""
            r"""|\b(?:rgba?|hsla?)\(\s*\d"""
        ),
        (),
    ),
    "colour-utility": (
        "Muted text is .vr-muted; no Bootstrap colour utility that bypasses the tokens",
        UNTHEMED_UTILITY,
        (),
    ),
    "card-markup": (
        "Panels and table cards only through {% panel %} / {% panel_section %}",
        re.compile(r"""class="[^"]*\bcard(?:-header|-body|-footer|-title)?\b"""),
        COMPONENT_DIRS,
    ),
    "alert-markup": (
        "Notices only through {% notice %} (or {% messages %})",
        re.compile(r"""class="[^"]*\balert\b"""),
        COMPONENT_DIRS,
    ),
    "list-state": (
        "Empty, no-results and filter-error states only through {% list_results %} / "
        "{% empty_state %}",
        re.compile(r"""kind=["']no-results["']|class="[^"]*\bvr-empty\b"""),
        COMPONENT_DIRS,
    ),
    "history-panel": (
        "History only through {% history_panel %} / {% history_item %}",
        re.compile(r"\bvr-timeline(?![\w-])|\bvr-history-item(?![\w-])"),
        COMPONENT_DIRS,
    ),
    "fact-row": (
        "Facts only through {% fact %}; no hand-written <dt>",
        re.compile(r"<dt\b"),
        COMPONENT_DIRS,
    ),
    "page-meta-list": (
        "Key facts under the title only through {% page_meta %}",
        re.compile(r"\bvr-page-meta\b"),
        COMPONENT_DIRS,
    ),
    "hand-pagination": (
        "Pagination only through {% pagination %} (or {% list_results %})",
        re.compile(r"""class="[^"]*\bpagination\b"""),
        COMPONENT_DIRS,
    ),
    "status-span": (
        "Status labels only through {% status %}",
        re.compile(r"""class="[^"]*\bvr-status\b"""),
        COMPONENT_DIRS,
    ),
    "breadcrumbs": (
        "Breadcrumbs only through {% breadcrumbs %}",
        re.compile(r"""class="[^"]*\bbreadcrumb(?:-item)?\b"""),
        COMPONENT_DIRS,
    ),
    "toolbar": (
        "List toolbars only through {% grid_toolbar %}",
        re.compile(r"""class="[^"]*\b(?:vr-grid-toolbar|vr-filterbar)\b"""),
        COMPONENT_DIRS,
    ),
    "form-actions": (
        "Form action rows only through {% form_actions %} (or {% form_page %})",
        re.compile(r"\bvr-form-actions\b"),
        COMPONENT_DIRS,
    ),
    "required-note": (
        "The required-fields sentence only through {% required_note %}",
        re.compile(r"Fields marked"),
        COMPONENT_DIRS,
    ),
    "raw-input": (
        "Inputs through form fields or the shared components (row_select, select_all, grid_search)",
        re.compile(r"""<input\b(?![^>]*\btype=["']hidden["'])"""),
        # The help drawer's reference filter: a search box over the open document, not a form.
        (*COMPONENT_DIRS, "pagedocs/templates/pagedocs/content.html"),
    ),
    "raw-select": (
        "Selects through form fields (the shared select widget), never a hand <select>",
        re.compile(r"<select\b"),
        COMPONENT_DIRS,
    ),
    "as-p": (
        "Render forms through {% form_page %} / {% field %}, not as_p, as_table or as_ul",
        re.compile(r"\.as_(?:p|table|ul)\b"),
        (),
    ),
    "form-novalidate": (
        "POST forms carry novalidate: the server validates and errors are shown inline",
        re.compile(r"""<form\b(?=[^>]*\bmethod=["']post["'])(?![^>]*\bnovalidate)[^>]*>""", re.I),
        COMPONENT_DIRS,
    ),
    "component-include": (
        "Shared components render through their {% load ui %} tags, never a plain include: a tag "
        "gives the component a context of its own (tests/test_include_isolation.py)",
        re.compile(
            r"""{%\s*include\s+["']includes/(?:"""
            + "|".join(sorted(map(re.escape, COMPONENTS)))
            + r""")\.html["']"""
        ),
        ("templates/includes/",),
    ),
    "page-own-h1": (
        "Pages set page_title in the view; the shell renders the one <h1>",
        own_h1,
        STANDALONE,
    ),
    "suppressed-header": (
        "Do not empty {% block page_header %}: the shell's header carries title, breadcrumbs "
        "and actions",
        suppressed_header,
        # The documentation's full-page fallback shows the document's own title.
        (*STANDALONE, "pagedocs/templates/pagedocs/page.html"),
    ),
    "header-primaries": (
        "At most one btn-primary in page_actions; further actions in {% more_actions %}",
        too_many_primaries,
        (),
    ),
}

# Rules not yet enforced: none. A new rule may start here while templates move onto a component;
# each entry names its remaining offenders, and the rule switches on when they are gone.
PENDING: set[str] = set()


def templates():
    dirs = [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]
    dirs += [Path(app.path) / "templates" for app in apps.get_app_configs()]
    for directory in dirs:
        if not directory.is_dir() or ROOT not in directory.parents or ".venv" in directory.parts:
            continue
        for path in sorted(directory.rglob("*.html")):
            yield path.relative_to(ROOT).as_posix(), path.read_text()


def strip_comments(source):
    source = re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", source, flags=re.S)
    source = re.sub(r"{#.*?#}", "", source, flags=re.S)
    return re.sub(r"<!--.*?-->", "", source, flags=re.S)


def exempt(name, owners):
    return any(name == o or (o.endswith("/") and name.startswith(o)) for o in owners)


def offenders(rule):
    _, check, owners = RULES[rule]
    found = []
    for name, source in templates():
        if exempt(name, DOCUMENTS) or exempt(name, owners):
            continue
        source = strip_comments(source)
        if check(source) if callable(check) else check.search(source):
            found.append(name)
    return found


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param(
            rule,
            marks=pytest.mark.xfail(
                reason="pages still migrating onto the components", strict=False
            )
            if rule in PENDING
            else (),
        )
        for rule in RULES
    ],
)
def test_templates_do_not_use_retired_patterns(rule):
    found = offenders(rule)
    assert not found, f"{rule}: {RULES[rule][0]}\n" + "\n".join(found)


def test_the_scanner_sees_the_templates():
    names = {name for name, _ in templates()}
    assert "templates/base.html" in names
    assert "templates/includes/status.html" in names
    assert any(name.startswith("quality/") or "/quality/" in name for name in names)
    assert len(names) > 100


def test_pending_rules_exist():
    assert PENDING <= set(RULES)


def test_header_primaries_counts_one_path_through_branches():
    primary = '<a class="btn btn-primary">Go</a>'
    exclusive = f"{{% if a %}}{primary}{{% else %}}{primary}{{% endif %}}"
    both = f"{primary}{{% if b %}}{primary}{{% endif %}}"
    assert most_primaries(exclusive) == 1
    assert most_primaries(both) == 2
    post = '{% post_button action=u label="Issue" variant="primary" %}'
    secondary = '{% post_button action=u label="Withdraw" %}'
    assert most_primaries(f"{post}{secondary}") == 1
    assert most_primaries(f"{post}{{% if b %}}{primary}{{% endif %}}") == 2


def test_unthemed_utilities_are_caught_and_themed_ones_allowed():
    assert UNTHEMED_UTILITY.search('<p class="text-body-secondary">')
    assert UNTHEMED_UTILITY.search('<div class="card bg-light">')
    assert not UNTHEMED_UTILITY.search('<p class="vr-muted text-danger">')
    assert not UNTHEMED_UTILITY.search('<button class="btn btn-danger">')
