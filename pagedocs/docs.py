"""Load page documentation files and map URL names to them.

Each ``docs/pages/*.md`` file starts with a small front matter block::

    ---
    title: Material lots
    urls: quality:lot_list
    views: quality.views.lot_list
    templates: quality/lot_list.html
    models: quality.Lot, core.RuleSet
    reviewed: 2026-11-10
    summary: Find a material lot, see where it stands and start a new lot in quarantine.
    ---

``urls`` lists every URL name (``namespace:name``) the file documents. Values are plain text;
lists are comma separated (optionally inside ``[...]``). No YAML dependency is needed.

The friendly layer is optional during its roll-out, but all or none: ``summary`` in the front
matter, then ``## Common tasks`` (``###`` task titles, each with a numbered list of steps) and
``## Good to know`` (a bulleted list) before the reference sections. ``[[Label]]`` in steps and
tips marks an exact on-screen label. The limits below are checked when a file is read.
"""

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.safestring import mark_safe

from .markdown import LABEL, render

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
TASKS_SECTION = "Common tasks"
TIPS_SECTION = "Good to know"
SUMMARY_MAX = 240
TASKS = (2, 5)
TASK_TITLE_MAX = 80
STEPS = (1, 4)
STEP_MAX = 200
TIPS = (3, 5)
TIP_MAX = 200
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_SECTION = re.compile(r"^## (.+?)\s*$", re.M)
_TASK = re.compile(r"^### (.+?)\s*$")
_STEP = re.compile(r"^\d+[.)]\s+(.*)$")
_TIP = re.compile(r"^[-*]\s+(.*)$")


@dataclass(frozen=True)
class Task:
    title: str
    steps: tuple[str, ...]


@dataclass(frozen=True)
class Section:
    title: str
    anchor: str
    heading: str  # the rendered <h3>, used when the reference is shown open
    html: str  # the rendered body under the heading


@dataclass(frozen=True)
class PageDoc:
    path: Path
    title: str
    urls: tuple[str, ...]
    reviewed: str
    body: str
    meta: dict = field(default_factory=dict)
    summary: str = ""
    tasks: tuple[Task, ...] = ()
    tips: tuple[str, ...] = ()

    @property
    def reference(self) -> tuple[Section, ...]:
        """The reference sections (all but the friendly layer), rendered once per file version."""
        return _rendered(self.path, self.path.stat().st_mtime_ns)

    @property
    def html(self):
        # Every part is already sanitized HTML from pagedocs.markdown.render.
        return mark_safe("\n".join(s.heading + s.html for s in self.reference))  # noqa: S308

    @property
    def sections(self):
        return [m.group(1).strip() for m in _SECTION.finditer(self.body)]


def docs_dir() -> Path:
    return Path(getattr(settings, "PAGEDOCS_DIR", settings.BASE_DIR / "docs" / "pages"))


def split_sections(body):
    """``[(title, text), ...]`` for each ``##`` section; text before the first one is dropped."""
    matches = list(_SECTION.finditer(body))
    ends = [m.start() for m in matches[1:]] + [len(body)]
    return [(m.group(1).strip(), body[m.end() : end]) for m, end in zip(matches, ends, strict=True)]


def label_problem(text):
    """Why ``text`` misuses the ``[[Label]]`` marker, or ``""``: every ``[[`` must close and
    markers cannot nest."""
    rest = LABEL.sub("", text)
    if "[[" in rest or "]]" in rest:
        return "has an unpaired or nested [[label]] marker"
    return ""


def _check_text(name, where, text, limit):
    if not text.strip() or len(text) > limit:
        raise ImproperlyConfigured(f"{name}: {where} must be 1-{limit} characters")
    if problem := label_problem(text):
        raise ImproperlyConfigured(f"{name}: {where} {problem}")


def _tasks(name, text):
    tasks, current = [], None
    for line in text.split("\n"):
        if not line.strip():
            continue
        if match := _TASK.match(line):
            current = (match.group(1), [])
            tasks.append(current)
        elif (match := _STEP.match(line)) and current:
            current[1].append(match.group(1).strip())
        elif line[:1] in (" ", "\t") and current and current[1]:
            current[1][-1] += " " + line.strip()
        else:
            raise ImproperlyConfigured(
                f"{name}: '{TASKS_SECTION}' holds only ### task titles and numbered steps: {line!r}"
            )
    if not TASKS[0] <= len(tasks) <= TASKS[1]:
        raise ImproperlyConfigured(f"{name}: '{TASKS_SECTION}' needs {TASKS[0]}-{TASKS[1]} tasks")
    for number, (title, steps) in enumerate(tasks, 1):
        if not title.strip() or len(title) > TASK_TITLE_MAX or "[[" in title:
            raise ImproperlyConfigured(
                f"{name}: task {number} needs a plain title of 1-{TASK_TITLE_MAX} characters"
            )
        if not STEPS[0] <= len(steps) <= STEPS[1]:
            raise ImproperlyConfigured(f"{name}: task {number} needs {STEPS[0]}-{STEPS[1]} steps")
        for index, step in enumerate(steps, 1):
            _check_text(name, f"task {number} step {index}", step, STEP_MAX)
    return tuple(Task(title, tuple(steps)) for title, steps in tasks)


def _tips(name, text):
    tips = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        if match := _TIP.match(line):
            tips.append(match.group(1).strip())
        elif line[:1] in (" ", "\t") and tips:
            tips[-1] += " " + line.strip()
        else:
            raise ImproperlyConfigured(
                f"{name}: '{TIPS_SECTION}' holds only a bulleted list: {line!r}"
            )
    if not TIPS[0] <= len(tips) <= TIPS[1]:
        raise ImproperlyConfigured(f"{name}: '{TIPS_SECTION}' needs {TIPS[0]}-{TIPS[1]} items")
    for index, tip in enumerate(tips, 1):
        _check_text(name, f"'{TIPS_SECTION}' item {index}", tip, TIP_MAX)
    return tuple(tips)


def _friendly(name, meta, body):
    """Validate the optional friendly layer; return ``(summary, tasks, tips)``."""
    sections = split_sections(body)
    titles = [title for title, _text in sections]
    texts = dict(sections)
    present = {
        "summary": "summary" in meta,
        TASKS_SECTION: TASKS_SECTION in texts,
        TIPS_SECTION: TIPS_SECTION in texts,
    }
    if not any(present.values()):
        return "", (), ()
    if not all(present.values()):
        missing = [key for key, there in present.items() if not there]
        raise ImproperlyConfigured(f"{name}: the friendly layer is all or none; it lacks {missing}")
    if titles.count(TASKS_SECTION) > 1 or titles.count(TIPS_SECTION) > 1:
        raise ImproperlyConfigured(f"{name}: friendly sections appear twice")
    if titles[:2] != [TASKS_SECTION, TIPS_SECTION]:
        raise ImproperlyConfigured(
            f"{name}: '{TASKS_SECTION}' then '{TIPS_SECTION}' come before the reference sections"
        )
    summary = meta["summary"]
    if not summary or len(summary) > SUMMARY_MAX or "[[" in summary:
        raise ImproperlyConfigured(
            f"{name}: summary must be plain text of 1-{SUMMARY_MAX} characters"
        )
    return summary, _tasks(name, texts[TASKS_SECTION]), _tips(name, texts[TIPS_SECTION])


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
    body = text[match.end() :]
    summary, tasks, tips = _friendly(path.name, meta, body)
    return PageDoc(
        path=path,
        title=meta["title"],
        urls=meta["urls"],
        reviewed=meta["reviewed"],
        body=body,
        meta=meta,
        summary=summary,
        tasks=tasks,
        tips=tips,
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
    used_ids = set()
    sections = []
    for title, text in split_sections(parse(path).body):
        if title in (TASKS_SECTION, TIPS_SECTION):
            continue
        heading = render(f"## {title}", used_ids=used_ids)
        anchor = re.search(r'id="([^"]+)"', heading).group(1)
        sections.append(Section(title, anchor, heading, render(text, used_ids=used_ids)))
    return tuple(sections)
