"""The entries as the application shows them, read from changelog.d/: once per process, or with
DEBUG on every change of a file (development).

Last seen is the per-user presentation preference ``whatsnew.seen`` (core/preferences.py): the id
of the newest entry the user was shown. Entries with a later id are new to them. It is set the
first time the shell renders for the user (nothing is new to a new account) and again whenever
What's new is opened.
"""

from functools import cache
from pathlib import Path

from django.conf import settings
from django.urls import NoReverseMatch, reverse

from core import preferences
from core.navigation import SECTIONS
from pagedocs.docs import doc_for
from pagedocs.markdown import render

from . import entries as changelog

SEEN_KEY = "whatsnew.seen"


def changelog_dir() -> Path:
    return Path(getattr(settings, "WHATSNEW_DIR", settings.BASE_DIR / "changelog.d"))


def _signature(directory):
    return tuple((p.name, p.stat().st_mtime_ns) for p in changelog.entry_files(directory))


@cache
def _load(directory, signature):
    entries, errors = changelog.load(directory)
    return tuple(entries), tuple(errors)


def load():
    """``(entries, errors)``: the valid entries, newest first, and a message per unreadable file.

    Outside DEBUG the files ship with the code and cannot change while the process runs, so they
    are read once per process (per directory) instead of stat'ed on every page. With DEBUG a
    changed, added or removed file is read again on the next page.
    """
    directory = changelog_dir()
    signature = _signature(directory) if settings.DEBUG else None
    return _load(str(directory), signature)


@cache
def _html(text):
    return render(text, heading_offset=3) if text else ""


def link_label(url_name):
    """The page a link names, by its documented title; '' when it is not a page."""
    try:
        reverse(url_name)
    except NoReverseMatch:
        return ""
    doc = doc_for(url_name)
    return doc.title if doc else ""


def reachable(url_name, flags):
    """Whether the sidebar would show the page's navigation home to someone with these flags
    (accounts.context_processors.account_navigation). Pages without one are not limited here;
    the page's own view still decides."""
    namespace = url_name.split(":", 1)[0]
    for section in SECTIONS:
        for item in section.items:
            if url_name in item.except_views:
                continue
            if namespace in item.namespaces or url_name in item.views:
                return all(
                    not need or flags.get(need) for need in (section.requires, item.requires)
                )
    return True


def seen(request):
    return preferences.for_request(request).get(SEEN_KEY) or ""


def unread_count(request):
    """How many entries are newer than the newest one this user has been shown.

    The first time the shell renders for someone without a mark (a new account), the newest
    entry is recorded as seen and nothing counts: the count means "changed since you last looked".
    """
    entries, _errors = load()
    if not seen(request):
        mark_seen(request, entries)
        return 0
    return len(changelog.unread(entries, seen(request)))


def mark_seen(request, entries):
    """Record that the user has been shown every entry; returns the previous last-seen id."""
    before = seen(request)
    newest = changelog.newest_id(entries)
    if newest and newest > before:
        preferences.save(request, SEEN_KEY, newest)
    return before


def shown_groups(entries, flags, before):
    """The groups of the page, each entry with its rendered text, link and whether it is new."""
    new = {e.id for e in changelog.unread(entries, before)}
    groups = []
    for group in changelog.grouped(entries):
        sections = []
        for section in group.sections:
            items = []
            for entry in section.entries:
                label = link_label(entry.link) if entry.link else ""
                visible = bool(label) and reachable(entry.link, flags)
                items.append(
                    {
                        "entry": entry,
                        "summary": _html(entry.summary),
                        "technical": _html(entry.technical),
                        "link_url": reverse(entry.link) if visible else "",
                        "link_label": label if visible else "",
                        "new": entry.id in new,
                    }
                )
            sections.append({"impact": section.impact, "label": section.label, "items": items})
        groups.append({"group": group, "sections": sections})
    return groups
