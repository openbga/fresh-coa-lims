"""Design tokens (docs/ui-standards.md, "Tokens").

Colours and lengths are defined once, in the Tokens section at the top of static/css/app.css, for
the light, dark and print palettes. Every rule after it, and every other first-party stylesheet,
uses the --vr-* tokens: no hex, rgb() or hsl() colour and no px or rem length, except the
dimensions allowed below with their reason. Lengths in em (relative to the element's own text)
are not scale steps and stay allowed.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
APP_CSS = ROOT / "static/css/app.css"
BASE = "/* " + "=" * 64 + " Base */"  # the header that ends the Tokens section

# First-party stylesheets checked in full (app.css is checked after its Tokens section).
STYLESHEETS = [
    "static/css/login.css",
    "static/css/controls.css",
    "pagedocs/static/pagedocs/pagedocs.css",
]
# Stylesheets another teammate is converting now: checked, but expected to fail until handed back.
PENDING = {}

# Properties that set one element's own size or position (a column, a field, a logo, a dialog).
# These are dimensions of that component, not steps on a shared scale; naming each as a token
# would only alias the value once.
DIMENSIONS = {
    "width",
    "height",
    "min-width",
    "min-height",
    "max-width",
    "max-height",
    "flex",
    "flex-basis",
    "grid-template-columns",
    "background-size",
    "background-position",
    "background-image",  # gradient stops that draw a decorative image (the sheet's punched holes)
    "transform",
    "--bs-offcanvas-width",  # the phone navigation sheet's width
    "--bs-tooltip-max-width",  # a tooltip's line length
    "--vr-sheet-margin",  # the sign-in sheet's punched margin
    "--pagedocs-width",  # the help drawer's default width; pagedocs.js stores the user's own
    # Keyboard scrolling clears a sticky column or the sticky action row: their sizes.
    "scroll-padding-bottom",
    "scroll-padding-block",
    "scroll-padding-inline-start",
}

# Literal values allowed in any property, with the reason.
VALUES = {
    "9999px": "the spread of an inset box-shadow that floods a cell with a wash colour",
}

COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(\s*[\d.]")
LENGTH = re.compile(r"(?<![\w.#-])-?\d*\.?\d+(?:px|rem)\b")
DECLARATION = re.compile(r"(--[\w-]+|[a-z-]+)\s*:\s*([^;{}]+);")


def without_comments(css):
    """Blank out comments, keeping line breaks so line numbers still match the file."""
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), css, flags=re.S)


def rules_after_tokens():
    """(first line number, text) of everything after the Tokens section, which ends at Base."""
    text = APP_CSS.read_text()
    head, marker, body = text.partition(BASE)
    assert marker, "app.css lost its Base section header"
    return head.count("\n") + 1, without_comments(marker + body)


def literal_problems(name, first, body):
    problems = []
    for match in DECLARATION.finditer(body):
        prop, value = match.group(1), " ".join(match.group(2).split())
        where = f"{name}:{first + body.count(chr(10), 0, match.start(2))} {prop}: {value}"
        if COLOUR.search(value):
            problems.append(f"{where} (colour literal: define a --vr-* colour token)")
        if prop in DIMENSIONS:
            continue
        if [v for v in LENGTH.findall(value) if v.lstrip("-") not in VALUES]:
            problems.append(f"{where} (length literal: use a --vr-space, --vr-font-size... token)")
    return problems


def test_app_css_rules_use_tokens_not_literal_colours_or_lengths():
    first, body = rules_after_tokens()
    problems = literal_problems("app.css", first, body)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "name",
    [
        *STYLESHEETS,
        *(
            pytest.param(name, marks=pytest.mark.xfail(reason=reason, strict=False))
            for name, reason in PENDING.items()
        ),
    ],
)
def test_other_stylesheets_use_tokens(name):
    problems = literal_problems(name, 1, without_comments((ROOT / name).read_text()))
    assert not problems, "\n".join(problems)


def test_every_token_used_is_defined():
    defined = set(re.findall(r"(--vr-[\w-]+)\s*:", APP_CSS.read_text()))
    problems = []
    for name in ["static/css/app.css", *STYLESHEETS, *PENDING]:
        path = ROOT / name
        if path.exists():
            used = set(re.findall(r"var\(\s*(--vr-[\w-]+)", path.read_text()))
            local = set(re.findall(r"(--vr-[\w-]+)\s*:", path.read_text()))
            problems += [f"{name}: {token}" for token in sorted(used - defined - local)]
    assert not problems, "tokens used but never defined:\n" + "\n".join(problems)


def test_rgb_tokens_match_their_colour():
    """Bootstrap needs some colours as "r, g, b" channels; each must equal its hex token."""
    head = APP_CSS.read_text().partition(BASE)[0]
    problems = []
    for block in re.findall(r"\{([^{}]*)\}", without_comments(head)):
        tokens = dict(re.findall(r"(--vr-[\w-]+)\s*:\s*([^;]+);", block))
        for name, channels in tokens.items():
            if not name.endswith("-rgb"):
                continue
            colour = tokens.get(name.removesuffix("-rgb"), "").strip()
            hex_ = colour.lstrip("#")
            if len(hex_) != 6 or channels.strip() != ", ".join(
                str(int(hex_[i : i + 2], 16)) for i in (0, 2, 4)
            ):
                problems.append(f"{name}: {channels.strip()} does not match {colour}")
    assert not problems, "\n".join(problems)


def test_every_palette_defines_the_same_colours():
    """Light, dark and print set every colour token, so no mode inherits another's colour."""
    head = without_comments(APP_CSS.read_text().partition(BASE)[0])
    light = re.search(r':root,\s*\[data-bs-theme="light"\]\s*\{([^{}]*)\}', head).group(1)
    dark = re.search(r'\[data-bs-theme="dark"\]\s*\{([^{}]*)\}', head).group(1)
    colours = {n for n, v in re.findall(r"(--vr-[\w-]+)\s*:\s*([^;]+);", light) if COLOUR.search(v)}
    missing = colours - set(re.findall(r"(--vr-[\w-]+)\s*:", dark))
    assert not missing, f"dark palette lacks {sorted(missing)}"


def test_bootstrap_semantic_colours_follow_the_status_tones():
    head = without_comments(APP_CSS.read_text().partition(BASE)[0])
    for tone, token in {
        "secondary": "neutral",
        "info": "info",
        "success": "success",
        "warning": "warning",
        "danger": "danger",
    }.items():
        assert f"--bs-{tone}: var(--vr-{token}-text);" in head
        assert f"--bs-{tone}-rgb: var(--vr-{token}-text-rgb);" in head
        assert f"--bs-{tone}-bg-subtle: var(--vr-{token}-bg);" in head
        assert f"--bs-{tone}-border-subtle: var(--vr-{token}-border);" in head
