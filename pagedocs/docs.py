"""Load page documentation files and map URL names to them.

Each ``docs/pages/*.md`` file starts with a small front matter block::

    ---
    title: Material lots
    urls: quality:lot_list
    views: quality.views.lot_list
    templates: quality/lot_list.html
    models: quality.Lot, core.RuleSet
    reviewed: 2026-11-10
    ---

``urls`` lists every URL name (``namespace:name``) the file documents. Values are plain text;
lists are comma separated (optionally inside ``[...]``). No YAML dependency is needed.
"""

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .markdown import render

LIST_KEYS = {"urls", "views", "templates", "models"}
REQUIRED_KEYS = {"title", "urls", "reviewed"}
REQUIRED_SECTIONS = (
    "Purpose",
    "Who can use it",
    "Layout",
    "Actions",
    "Fields",
    "Rules and hidden logic",
    "Related pages",
)
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass(frozen=True)
class PageDoc:
    path: Path
    title: str
    urls: tuple[str, ...]
    reviewed: str
    body: str
    meta: dict = field(default_factory=dict)

    @property
    def html(self):
        return _rendered(self.path, self.path.stat().st_mtime_ns)

    @property
    def sections(self):
        return [m.group(1).strip() for m in re.finditer(r"^## (.+)$", self.body, re.M)]


def docs_dir() -> Path:
    return Path(getattr(settings, "PAGEDOCS_DIR", settings.BASE_DIR / "docs" / "pages"))


def parse(path: Path) -> PageDoc:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = _FRONT.match(text)
    if not match:
        raise ImproperlyConfigured(f"{path.name}: missing front matter block")
    meta = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ImproperlyConfigured(f"{path.name}: front matter line without key: {line!r}")
        key, value = key.strip(), value.strip()
        if key in LIST_KEYS:
            value = tuple(v.strip() for v in value.strip("[]").split(",") if v.strip())
        meta[key] = value
    missing = REQUIRED_KEYS - meta.keys()
    if missing:
        raise ImproperlyConfigured(f"{path.name}: front matter lacks {sorted(missing)}")
    return PageDoc(
        path=path,
        title=meta["title"],
        urls=meta["urls"],
        reviewed=meta["reviewed"],
        body=text[match.end() :],
        meta=meta,
    )


def all_docs() -> list[PageDoc]:
    directory = docs_dir()
    if not directory.is_dir():
        return []
    return [parse(p) for p in sorted(directory.glob("*.md")) if not p.name.startswith("_")]


def _signature():
    directory = docs_dir()
    if not directory.is_dir():
        return ()
    return tuple((p.name, p.stat().st_mtime_ns) for p in sorted(directory.glob("*.md")))


@cache
def _index(signature) -> dict[str, PageDoc]:
    index = {}
    for doc in all_docs():
        for name in doc.urls:
            index.setdefault(name, doc)  # duplicates are rejected by the coverage test
    return index


def doc_for(url_name: str) -> PageDoc | None:
    """Return the doc covering ``url_name`` (``namespace:name``), re-reading changed files."""
    return _index(_signature()).get(url_name)


@cache
def _rendered(path, mtime_ns):
    return render(parse(path).body)
