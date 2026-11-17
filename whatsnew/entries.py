"""What's new: the entries in ``changelog.d/`` and the changelog generated from them.

One Markdown file per change, named ``YYYY-MM-DD-short-slug.md``::

    ---
    date: 2026-11-17
    type: added
    impact: high
    title: Reject a lot in quarantine with a signed record
    area: Lots
    link: quality:lot_list
    pr: 44
    ---
    One to three plain sentences for the people who use the application.

    ## Technical notes

    Optional: migrations, settings, schema identifiers, dependencies, upgrade steps.

The front matter is flat ``key: value`` lines (no YAML dependency). ``date``, ``type``,
``impact`` and ``title`` are required; ``area``, ``link`` (a URL name the application can
reverse without arguments; checked by ``manage.py changelog``) and ``pr`` are optional. The
filename's date is the entry's date. The summary is the text before ``## Technical notes``.

This module does not import Django: ``manage.py changelog`` writes CHANGELOG.md from it, and the
What's new page (whatsnew/views.py) shows the same groups in the same order. How to write an entry:
the ``changelog-entry`` skill (.agents/skills/changelog-entry/SKILL.md) and CONTRIBUTING.md.
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date as Date
from itertools import groupby
from pathlib import Path

TYPES = {
    "added": "Added",
    "changed": "Changed",
    "fixed": "Fixed",
    "removed": "Removed",
    "deprecated": "Deprecated",
    "security": "Security",
}  # Keep a Changelog 1.1.0, https://keepachangelog.com/en/1.1.0/
IMPACTS = {"high": "High impact", "medium": "Medium impact", "low": "Low impact"}
REQUIRED = ("date", "type", "impact", "title")
OPTIONAL = ("area", "link", "pr")
TECHNICAL_HEADING = "## Technical notes"
TITLE_MAX = 120
AREA_MAX = 40
PULL_URL = "https://github.com/openbga/qm-lims/pull/{}"
GENERATED_NOTE = (
    "<!-- Generated from changelog.d/ by `uv run python manage.py changelog`. Do not edit this "
    "file by hand: add an entry file to changelog.d/ instead (CONTRIBUTING.md, "
    '"Changelog entries"). -->'
)

FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
LINK = re.compile(r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_KEY = re.compile(r"^[a-z]+$")


class EntryError(ValueError):
    """An entry file that cannot be read; the message names the file and the key."""


@dataclass(frozen=True)
class Entry:
    id: str  # the filename without .md; sorts by date, then slug
    date: Date
    type: str
    impact: str
    title: str
    summary: str
    technical: str = ""
    area: str = ""
    link: str = ""
    pr: int | None = None

    @property
    def type_label(self):
        return TYPES[self.type]

    @property
    def pr_url(self):
        return PULL_URL.format(self.pr) if self.pr else ""


@dataclass(frozen=True)
class Section:
    impact: str
    label: str
    entries: tuple[Entry, ...]


@dataclass(frozen=True)
class Group:
    year: int
    month: int
    start: Date
    end: Date
    sections: tuple[Section, ...]

    @property
    def label(self):
        return f"{calendar.month_name[self.month]} {self.year}"

    @property
    def anchor(self):
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def range(self):
        """The dates the group's entries cover, ``2026-11-03 to 2026-11-17`` or one date."""
        if self.start == self.end:
            return self.start.isoformat()
        return f"{self.start.isoformat()} to {self.end.isoformat()}"

    @property
    def count(self):
        return sum(len(section.entries) for section in self.sections)


def _fail(name, message):
    raise EntryError(f"changelog.d/{name}: {message}")


def parse_text(name, text):
    """The entry in ``text`` of the file ``name``. Raises EntryError naming file and key."""
    filename = FILENAME.match(name)
    if not filename:
        _fail(name, "the file name must be YYYY-MM-DD-short-slug.md (lowercase, digits, hyphens)")
    text = text.replace("\r\n", "\n")
    match = _FRONT.match(text)
    if not match:
        _fail(name, "missing the front matter block between two '---' lines")
    meta = {}
    for line in match.group(1).split("\n"):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not _KEY.match(key):
            _fail(name, f"front matter line is not 'key: value': {line!r}")
        if key not in REQUIRED + OPTIONAL:
            known = ", ".join(REQUIRED + OPTIONAL)
            _fail(name, f"key '{key}' is unknown (known keys: {known})")
        if key in meta:
            _fail(name, f"key '{key}' appears twice")
        meta[key] = value
    for key in REQUIRED:
        if not meta.get(key):
            _fail(name, f"key '{key}' is missing or empty")

    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
            raise ValueError
        when = Date.fromisoformat(meta["date"])
    except ValueError:
        _fail(name, f"key 'date': {meta['date']!r} is not a date (YYYY-MM-DD)")
    if meta["date"] != filename.group(1):
        _fail(name, f"key 'date': {meta['date']} differs from the date in the file name")
    if meta["type"] not in TYPES:
        _fail(name, f"key 'type': {meta['type']!r} is not one of {', '.join(TYPES)}")
    if meta["impact"] not in IMPACTS:
        _fail(name, f"key 'impact': {meta['impact']!r} is not one of {', '.join(IMPACTS)}")
    title = meta["title"]
    if len(title) > TITLE_MAX or title.endswith(".") or not title[0].isupper():
        _fail(
            name,
            f"key 'title': start with a capital letter, end without a period, at most "
            f"{TITLE_MAX} characters",
        )
    area = meta.get("area", "")
    if "area" in meta and not 1 <= len(area) <= AREA_MAX:
        _fail(name, f"key 'area': 1-{AREA_MAX} characters")
    link = meta.get("link", "")
    if "link" in meta and not LINK.match(link):
        _fail(name, f"key 'link': {link!r} is not a URL name such as quality:lot_list")
    pr = None
    if "pr" in meta:
        if not re.fullmatch(r"[1-9]\d{0,5}", meta["pr"]):
            _fail(name, f"key 'pr': {meta['pr']!r} is not a pull request number")
        pr = int(meta["pr"])

    lines = [line.rstrip() for line in text[match.end() :].split("\n")]
    split = lines.index(TECHNICAL_HEADING) if TECHNICAL_HEADING in lines else len(lines)
    summary = "\n".join(lines[:split]).strip()
    technical = "\n".join(lines[split + 1 :]).strip()
    if not summary:
        _fail(name, "the summary (the text before '## Technical notes') is empty")
    for part, label in ((summary, "summary"), (technical, "technical notes")):
        if re.search(r"^#{1,6} ", part, re.M):
            _fail(name, f"the {label} part has a heading; only '{TECHNICAL_HEADING}' is allowed")
    return Entry(
        id=name[:-3],
        date=when,
        type=meta["type"],
        impact=meta["impact"],
        title=title,
        summary=summary,
        technical=technical,
        area=area,
        link=link,
        pr=pr,
    )


def entry_files(directory):
    """The ``*.md`` files of the directory, sorted by name; none when it does not exist."""
    directory = Path(directory)
    return sorted(directory.glob("*.md")) if directory.is_dir() else []


def load(directory):
    """``(entries, errors)``: every valid entry, newest first, and one message per bad file."""
    entries, errors = [], []
    for path in entry_files(directory):
        try:
            entries.append(parse_text(path.name, path.read_text(encoding="utf-8")))
        except EntryError as error:
            errors.append(str(error))
    return ordered(entries), errors


def ordered(entries):
    """Newest first, then by title (the order inside an impact section)."""
    by_title = sorted(entries, key=lambda e: (e.title.casefold(), e.id))
    return sorted(by_title, key=lambda e: e.date, reverse=True)


def grouped(entries):
    """Calendar months, newest first; inside each, the impact sections that have entries."""
    groups = []
    entries = ordered(entries)
    for (year, month), items in groupby(entries, key=lambda e: (e.date.year, e.date.month)):
        items = list(items)
        sections = tuple(
            Section(impact, label, tuple(e for e in items if e.impact == impact))
            for impact, label in IMPACTS.items()
            if any(e.impact == impact for e in items)
        )
        dates = [e.date for e in items]
        groups.append(Group(year, month, min(dates), max(dates), sections))
    return groups


def newest_id(entries):
    """The id of the newest entry (what a reader has seen once the list is shown), or ''."""
    return max((e.id for e in entries), default="")


def unread(entries, seen):
    """Entries newer than ``seen``, the newest entry id the reader saw. Without a mark nothing
    is unread: someone who has not used the application before has nothing new to catch up on."""
    if not seen:
        return []
    return [e for e in entries if e.id > seen]


def _indent(text, prefix):
    return "\n".join(
        prefix + line if line.strip() else prefix.rstrip() for line in text.split("\n")
    )


def render_changelog(entries, link_label=None):
    """CHANGELOG.md for the entries. ``link_label(url_name)`` names a page (default: the name)."""
    link_label = link_label or (lambda name: name)
    out = [
        GENERATED_NOTE,
        "",
        "# Changelog",
        "",
        "What changed in OpenBGA QM LIMS, newest first: grouped by month, then ranked by impact. "
        "The application shows the same list under **What's new**. Each change is a file in "
        "[changelog.d/](changelog.d/); entry types follow "
        "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project is pre-1.0 and "
        "does not yet promise a stable interface.",
    ]
    for group in grouped(entries):
        out += ["", f"## {group.label} ({group.range})"]
        for section in group.sections:
            out += ["", f"### {section.label}", ""]
            for entry in section.entries:
                facts = [entry.area] if entry.area else []
                facts.append(entry.date.isoformat())
                if entry.pr:
                    facts.append(f"[#{entry.pr}]({entry.pr_url})")
                out.append(f"- **{entry.type_label}**: {entry.title} · {' · '.join(facts)}")
                out += ["", _indent(entry.summary, "  ")]
                if entry.link:
                    out += ["", f"  In the application: **{link_label(entry.link)}**"]
                if entry.technical:
                    notes = "**Technical notes**\n\n" + entry.technical
                    out += ["", _indent(notes, "  > ")]
                out.append("")
            out.pop()
    if not entries:
        out += ["", "No changes are recorded yet."]
    return "\n".join(out) + "\n"
