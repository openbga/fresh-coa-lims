"""What's new in the application: the list, its states, the link rules and the unread indicator."""

import json
import re

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from core.models import UserPreference
from core.preferences import clean
from whatsnew import catalogue
from whatsnew.catalogue import SEEN_KEY

pytestmark = pytest.mark.django_db


def write(
    directory, name, *, impact="high", kind="added", title=None, link="", body=None, fresh=True
):
    """Write an entry; ``fresh`` drops the per-process read, as a new deployment would."""
    day = name[:10]
    lines = [
        "---",
        f"date: {day}",
        f"type: {kind}",
        f"impact: {impact}",
        f"title: {title or 'Change ' + name[11:]}",
    ]
    lines += [f"link: {link}"] if link else []
    lines += ["pr: 7", "---", body or f"Summary of {name[11:]}.", ""]
    (directory / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")
    if fresh:
        catalogue._load.cache_clear()


@pytest.fixture
def entries(tmp_path, settings):
    directory = tmp_path / "changelog.d"
    directory.mkdir()
    settings.WHATSNEW_DIR = directory
    settings.CHANGELOG_PATH = tmp_path / "CHANGELOG.md"
    return directory


@pytest.fixture
def person(django_user_model):
    def make(username, *roles):
        user = django_user_model.objects.create_user(username, password="synthetic-pass-1")
        for role in roles:
            user.groups.add(Group.objects.get_or_create(name=role)[0])
        return user

    return make


def topbar_button(client):
    page = client.get(reverse("accounts:access")).content.decode()
    match = re.search(r"<a [^>]*data-whatsnew-button[^>]*>.*?</a>", page, re.S)
    assert match, "every signed-in page carries the What's new link"
    return match.group(0)


def test_signed_out_visitors_are_sent_to_sign_in(client, entries):
    response = client.get(reverse("whatsnew:index"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_post_is_not_allowed(client, entries, person):
    client.force_login(person("analyst.test", "analyst"))
    assert client.post(reverse("whatsnew:index")).status_code == 405


def test_the_list_shows_months_impact_and_entries_in_order(client, entries, person):
    write(entries, "2026-10-30-october-fix", impact="low", kind="fixed", title="An October fix")
    write(entries, "2026-11-03-early", impact="high", title="Early high")
    write(entries, "2026-11-17-late", impact="high", title="Late high")
    write(entries, "2026-11-12-medium", impact="medium", kind="changed", title="A medium change")
    (entries / "2026-11-12-medium.md").write_text(
        (entries / "2026-11-12-medium.md").read_text()
        + "\n## Technical notes\n\nNew setting `EXAMPLE_SETTING`.\n"
    )
    client.force_login(person("analyst.test", "analyst"))
    response = client.get(reverse("whatsnew:index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "<title>What&#x27;s new · OpenBGA QM LIMS</title>" in body
    order = [
        "November 2026",
        "2026-11-03 to 2026-11-17",
        "High impact",
        "Late high",
        "Early high",
        "Medium impact",
        "A medium change",
        "October 2026",
        "Low impact",
        "An October fix",
    ]
    positions = [body.index(text) for text in order]
    assert positions == sorted(positions)
    assert ">Added</span>" in body and ">Changed</span>" in body and ">Fixed</span>" in body
    assert '<time datetime="2026-11-17">2026-11-17</time>' in body
    assert "<p>Summary of late.</p>" in body
    assert "<summary>" in body and "<code>EXAMPLE_SETTING</code>" in body
    assert 'href="https://github.com/openbga/qm-lims/pull/7"' in body
    assert body.count("data-whatsnew-entry=") == 4


def test_entry_text_is_escaped(client, entries, person):
    write(entries, "2026-11-17-escape", body="<script>alert(1)</script> and [x](javascript:1)")
    client.force_login(person("analyst.test", "analyst"))
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "<script>alert(1)" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert 'href="javascript' not in body


def test_a_link_opens_the_page_for_those_who_may_see_it(client, entries, person):
    write(entries, "2026-11-17-lots", link="quality:lot_list")
    write(entries, "2026-11-16-users", link="accounts:user_list")
    client.force_login(person("analyst.test", "analyst"))
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert f'href="{reverse("quality:lot_list")}"' in body
    assert "Material lots</a>" in body
    # Users and roles is an administrator's page: an analyst is not sent there.
    assert f'href="{reverse("accounts:user_list")}"' not in body
    client.force_login(person("admin.test", "admin"))
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert f'href="{reverse("accounts:user_list")}"' in body


def test_an_account_without_a_role_reads_it_too(client, entries, person):
    write(entries, "2026-11-17-lots", link="quality:lot_list")
    client.force_login(person("no.role"))
    response = client.get(reverse("whatsnew:index"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Change lots" in body
    assert f'href="{reverse("quality:lot_list")}"' not in body  # no workspace for this account


def test_no_entries_shows_the_empty_state(client, entries, person):
    client.force_login(person("analyst.test", "analyst"))
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "No changes are recorded yet" in body
    assert "data-whatsnew-unread" not in topbar_button(client)


def test_an_unreadable_entry_is_reported_and_the_rest_listed(client, entries, person):
    write(entries, "2026-11-17-good")
    (entries / "2026-11-16-bad.md").write_text("---\ndate: 2026-11-16\n---\nNo type.\n")
    client.force_login(person("analyst.test", "analyst"))
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "Some changes could not be read" in body
    assert "changelog.d/2026-11-16-bad.md: key &#x27;type&#x27; is missing or empty" in body
    assert "Change good" in body
    assert "No changes are recorded yet" not in body


def test_a_new_account_sees_no_indicator_and_its_first_page_sets_the_mark(client, entries, person):
    write(entries, "2026-11-10-first")
    write(entries, "2026-11-12-second")
    user = person("analyst.test", "analyst")
    client.force_login(user)
    assert not UserPreference.objects.filter(user=user, key=SEEN_KEY).exists()

    button = topbar_button(client)
    assert 'aria-label="What\'s new"' in button and 'title="What\'s new"' in button
    assert "data-whatsnew-unread" not in button
    assert UserPreference.objects.get(user=user, key=SEEN_KEY).value == "2026-11-12-second"

    # The list still shows every change, none of them marked New.
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert body.count("data-whatsnew-entry=") == 2
    assert 'data-tone="info"' not in body and "new since you last opened" not in body


def test_opening_the_list_first_also_sets_the_mark(client, entries, person):
    write(entries, "2026-11-10-first")
    user = person("analyst.test", "analyst")
    client.force_login(user)
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert body.count("data-whatsnew-entry=") == 1 and 'data-tone="info"' not in body
    assert UserPreference.objects.get(user=user, key=SEEN_KEY).value == "2026-11-10-first"


def test_no_entries_leave_no_mark_until_there_are_some(client, entries, person):
    user = person("analyst.test", "analyst")
    client.force_login(user)
    assert "data-whatsnew-unread" not in topbar_button(client)
    assert not UserPreference.objects.filter(user=user, key=SEEN_KEY).exists()
    write(entries, "2026-11-10-first")
    assert "data-whatsnew-unread" not in topbar_button(client)
    assert UserPreference.objects.get(user=user, key=SEEN_KEY).value == "2026-11-10-first"


def test_the_indicator_counts_changes_since_the_mark_and_opening_the_list_clears_it(
    client, entries, person
):
    write(entries, "2026-11-10-first")
    user = person("analyst.test", "analyst")
    client.force_login(user)
    assert "data-whatsnew-unread" not in topbar_button(client)  # sets the mark
    write(entries, "2026-11-12-second")
    write(entries, "2026-11-13-third")

    button = topbar_button(client)
    assert 'aria-label="What\'s new: 2 new changes"' in button
    assert 'title="What\'s new: 2 new changes"' in button
    assert ">What's new</span>" in button
    assert re.search(r"data-whatsnew-unread>2</span>", button)

    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "2 changes are new since you last opened this page" in body
    assert body.count("data-whatsnew-entry=") == 3  # every change is listed
    for entry_id, new in (
        ("2026-11-13-third", True),
        ("2026-11-12-second", True),
        ("2026-11-10-first", False),
    ):
        item = body.split(f'data-whatsnew-entry="{entry_id}"', 1)[1].split("</li>", 1)[0]
        assert ('data-tone="info"' in item) is new
    assert UserPreference.objects.get(user=user, key=SEEN_KEY).value == "2026-11-13-third"
    assert 'aria-current="page"' in re.search(r"<a [^>]*data-whatsnew-button[^>]*>", body).group(0)

    button = topbar_button(client)
    assert 'aria-label="What\'s new"' in button and "data-whatsnew-unread" not in button
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "new since you last opened" not in body and 'data-tone="info"' not in body

    write(entries, "2026-11-17-fourth")
    button = topbar_button(client)
    assert 'aria-label="What\'s new: 1 new change"' in button
    body = client.get(reverse("whatsnew:index")).content.decode()
    assert "1 change is new since you last opened this page" in body


def test_last_seen_is_per_user(client, entries, person):
    write(entries, "2026-11-10-first")
    first, second = person("first.test", "analyst"), person("second.test", "analyst")
    for user in (first, second):
        client.force_login(user)
        topbar_button(client)  # each account gets its own mark
    write(entries, "2026-11-12-second")
    client.force_login(first)
    client.get(reverse("whatsnew:index"))
    assert "data-whatsnew-unread" not in topbar_button(client)
    client.force_login(second)
    assert "data-whatsnew-unread" in topbar_button(client)


def test_last_seen_is_set_by_the_server_only(client, entries, person):
    client.force_login(person("analyst.test", "analyst"))
    response = client.post(
        reverse("core:preference"),
        json.dumps({"key": SEEN_KEY, "value": "2099-01-01-everything"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert clean(SEEN_KEY, "2026-11-17-a-change") == "2026-11-17-a-change"
    for value in ("2026-11-17", "../etc", "2026-11-17-A", 7, None, "2026-11-17-" + "a" * 120):
        assert clean(SEEN_KEY, value) is None


def test_more_than_99_unseen_changes_show_as_99_plus(client, entries, person):
    user = person("analyst.test", "analyst")
    UserPreference.objects.create(user=user, key=SEEN_KEY, value="2026-11-09-older")
    for number in range(100):
        write(entries, f"2026-11-10-change-{number:03d}")
    client.force_login(user)
    button = topbar_button(client)
    assert "What's new: 100 new changes" in button
    assert "data-whatsnew-unread>99+</span>" in button


# The command that writes CHANGELOG.md


def test_the_command_writes_the_changelog_and_check_mode_accepts_it(entries, settings, capsys):
    write(entries, "2026-11-17-lots", link="quality:lot_list")
    call_command("changelog")
    text = settings.CHANGELOG_PATH.read_text()
    assert "- **Added**: Change lots · 2026-11-17 · [#7]" in text
    assert "In the application: **Material lots**" in text
    call_command("changelog", "--check")
    assert "CHANGELOG.md is current (1 entries)." in capsys.readouterr().out


def test_check_mode_refuses_a_hand_edited_or_stale_changelog(entries, settings):
    write(entries, "2026-11-17-lots")
    call_command("changelog")
    path = settings.CHANGELOG_PATH
    path.write_text(path.read_text() + "\n- A bullet added by hand.\n")
    with pytest.raises(CommandError) as raised:
        call_command("changelog", "--check")
    message = str(raised.value)
    assert "never edit it by hand" in message
    assert "move each change into an entry file in\n  changelog.d/" in message
    assert "uv run python manage.py changelog" in message
    assert "+- A bullet added by hand." in message
    call_command("changelog")
    write(entries, "2026-11-18-later")  # a new entry without regenerating
    with pytest.raises(CommandError, match="is not what changelog.d/ generates"):
        call_command("changelog", "--check")


def test_the_command_refuses_invalid_entries_and_links(entries, settings):
    write(entries, "2026-11-17-record", link="quality:lot_detail")  # needs a lot
    write(entries, "2026-11-16-nowhere", link="quality:no_such_page")
    with pytest.raises(CommandError) as raised:
        call_command("changelog")
    message = str(raised.value)
    assert "changelog.d/2026-11-17-record.md: key 'link': 'quality:lot_detail'" in message
    assert "changelog.d/2026-11-16-nowhere.md: key 'link'" in message
    assert not settings.CHANGELOG_PATH.exists()
    (entries / "2026-11-15-bad.md").write_text("---\ndate: 2026-11-15\n---\nText.\n")
    with pytest.raises(CommandError, match="2026-11-15-bad.md: key 'type' is missing"):
        call_command("changelog", "--check")


def test_the_committed_changelog_is_current():
    """CHANGELOG.md is generated from changelog.d/ (CI runs the same check)."""
    call_command("changelog", "--check")


# How often the entry files are read


def test_outside_debug_the_entries_are_read_once_per_process(entries, settings, monkeypatch):
    settings.DEBUG = False
    write(entries, "2026-11-10-first")
    first = catalogue.load()
    assert [e.id for e in first[0]] == ["2026-11-10-first"]
    stats = []
    monkeypatch.setattr(catalogue, "_signature", lambda directory: stats.append(directory))
    write(entries, "2026-11-12-second", fresh=False)  # cannot happen in a deployment
    assert catalogue.load() is first
    assert stats == []  # no file is stat'ed on later pages


def test_with_debug_a_changed_entry_is_read_again(entries, settings):
    settings.DEBUG = True
    write(entries, "2026-11-10-first")
    first = catalogue.load()
    assert catalogue.load() is first  # unchanged files: the same read
    write(entries, "2026-11-12-second", fresh=False)
    assert [e.id for e in catalogue.load()[0]] == ["2026-11-12-second", "2026-11-10-first"]
    (entries / "2026-11-12-second.md").unlink()
    assert [e.id for e in catalogue.load()[0]] == ["2026-11-10-first"]
