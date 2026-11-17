"""Icons come only from Bootstrap Icons (docs/ui-standards.md, "Icons").

Every icon is a symbol copied verbatim from Bootstrap Icons 1.13.2 into static/img/icons.svg
(static/vendor/README.md records the package and its integrity) and rendered through {% icon %}
(templates/includes/icon.html) or window.vrUi.icon (static/js/app.js). The only other drawings
are the brand mark (static/img/mark.svg) and the sign-in illustration, both files.
"""

import re
from pathlib import Path

from django.conf import settings

from tests.test_ui_standards import strip_comments, templates

ROOT = Path(settings.BASE_DIR)
SPRITE = ROOT / "static/img/icons.svg"
APP_CSS = ROOT / "static/css/app.css"

SVG_TEMPLATES = {"templates/includes/icon.html"}

# SVG data URIs app.css may keep, by the path that identifies each, with the reason.
DATA_URIS = {
    "d='m6 10 3 3 6-6'": "Bootstrap's own checkbox tick, in the dark-mode ink (a data URI cannot "
    "read a CSS variable)",
    "d='M6 10h8'": "Bootstrap's own indeterminate checkbox bar, in the dark-mode ink",
}


def symbols():
    return re.findall(r"<symbol\b[^>]*>", SPRITE.read_text())


SKIPPED_DIRS = {".venv", ".local", "build", "vendor", "staticfiles", "node_modules"}


def scripts():
    for path in sorted(ROOT.glob("**/static/**/*.js")):
        if not SKIPPED_DIRS & set(path.parts):
            yield path.relative_to(ROOT).as_posix(), path.read_text()


def test_sprite_is_the_pinned_bootstrap_icons_subset():
    text = SPRITE.read_text()
    assert "Bootstrap Icons 1.13.2" in text
    assert (
        "bootstrap-icons (subset) | 1.13.2 | " + str(len(symbols())) + " icons"
        in (ROOT / "static/vendor/README.md").read_text()
    ), "static/vendor/README.md must state the sprite's icon count"


def test_templates_draw_no_svg_of_their_own():
    offenders = [
        name
        for name, source in templates()
        if name not in SVG_TEMPLATES and re.search(r"<svg\b", strip_comments(source))
    ]
    assert not offenders, f"Use {{% icon %}}, not inline <svg>: {offenders}"


def test_scripts_build_icons_only_through_vrui_icon():
    found = []
    for name, source in scripts():
        for match in re.finditer(r"<svg\b|createElementNS\([^)]*svg", source):
            line = source[: match.start()].count("\n") + 1
            found.append(f"{name}:{line}")
    assert len(found) == 1 and found[0].startswith("static/js/app.js:"), (
        f"Only window.vrUi.icon (static/js/app.js) builds SVG: {found}"
    )


def test_sprite_symbols_are_named_bootstrap_icons():
    ids = []
    for tag in symbols():
        ident = re.search(r'\bid="([^"]*)"', tag)
        ids.append(ident.group(1) if ident else "")
        assert ident and re.fullmatch(r"i-[a-z0-9]+(?:-[a-z0-9]+)*", ident.group(1)), tag
        assert 'viewBox="0 0 16 16"' in tag, f"{tag}: Bootstrap Icons are drawn on 0 0 16 16"
    assert len(ids) == len(set(ids)), "a symbol id appears twice in icons.svg"


def test_every_icon_named_in_code_is_in_the_sprite():
    from core.navigation import SECTIONS

    available = set(re.findall(r'<symbol\b[^>]*\bid="i-([^"]+)"', SPRITE.read_text()))
    named = {item.icon for section in SECTIONS for item in section.items if item.icon}
    for _, source in templates():
        named |= set(re.findall(r'includes/icon\.html"\s+with\s+name="([\w-]+)"', source))
        named |= set(re.findall(r'{%\s*icon\s+name="([\w-]+)"', source))
        named |= set(re.findall(r'\bicon="([\w-]+)"', source))
    for _, source in scripts():
        named |= set(re.findall(r"""\bicon\(\s*["']([\w-]+)["']""", source))
        named |= set(re.findall(r"""\[\s*["'](?:up|down)["']\s*,\s*["']([\w-]+)["']""", source))
    assert named, "the scan found no icon names"
    assert not named - available, f"missing from static/img/icons.svg: {sorted(named - available)}"


def test_css_svg_images_are_bootstrap_images():
    css = APP_CSS.read_text()
    uris = re.findall(r"""url\(\s*["']?data:image/svg\+xml[^)]*""", css)
    unknown = [uri[:90] for uri in uris if sum(key in uri for key in DATA_URIS) != 1]
    assert not unknown, f"SVG data URIs that are not on the allowlist: {unknown}"


def test_status_glyphs_are_icons_not_css_shapes():
    css = APP_CSS.read_text()
    assert not re.search(r"\.vr-status[^{]*::(?:before|after)", css)
    status = (ROOT / "templates/includes/status.html").read_text()
    assert re.search(r"{%\s*icon\s+name=glyph", status)
