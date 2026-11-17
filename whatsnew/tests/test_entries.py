"""Entry files of changelog.d/: parsing, validation, order, grouping and CHANGELOG.md layout."""

from datetime import date
from textwrap import dedent

import pytest

from whatsnew import entries as changelog
from whatsnew.entries import EntryError, grouped, load, ordered, parse_text, render_changelog

GOOD = dedent(
    """\
    ---
    date: 2026-11-17
    type: added
    impact: high
    title: Reject a lot in quarantine with a signed record
    area: Lots
    link: quality:lot_list
    pr: 44
    ---
    A quality person rejects a lot with a **signature**.

    ## Technical notes

    Migration `quality.0012_lot_rejection`.
    """
)
NAME = "2026-11-17-reject-a-lot.md"


def entry(day, slug, impact="medium", title=None, kind="changed"):
    when = date.fromisoformat(day)
    return changelog.Entry(
        id=f"{day}-{slug}",
        date=when,
        type=kind,
        impact=impact,
        title=title or slug.replace("-", " ").capitalize(),
        summary=f"Summary of {slug}.",
    )


def test_a_complete_entry_is_read():
    parsed = parse_text(NAME, GOOD)
    assert parsed.id == "2026-11-17-reject-a-lot"
    assert parsed.date == date(2026, 11, 17)
    assert (parsed.type, parsed.impact, parsed.area, parsed.link, parsed.pr) == (
        "added",
        "high",
        "Lots",
        "quality:lot_list",
        44,
    )
    assert parsed.type_label == "Added"
    assert parsed.summary == "A quality person rejects a lot with a **signature**."
    assert parsed.technical == "Migration `quality.0012_lot_rejection`."
    assert parsed.pr_url == "https://github.com/openbga/qm-lims/pull/44"


def test_optional_keys_and_technical_notes_may_be_left_out():
    text = "---\ndate: 2026-11-17\ntype: fixed\nimpact: low\ntitle: Small fix\n---\nFixed.\n"
    parsed = parse_text(NAME, text.replace("\n", "\r\n"))
    assert (parsed.area, parsed.link, parsed.pr, parsed.technical) == ("", "", None, "")
    assert parsed.summary == "Fixed."


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("type: added", "type: improved"), "key 'type': 'improved' is not one of added,"),
        (("impact: high", "impact: huge"), "key 'impact': 'huge' is not one of high, medium, low"),
        (("date: 2026-11-17", "date: 2026-13-01"), "key 'date': '2026-13-01' is not a date"),
        (("date: 2026-11-17", "date: 20261117"), "key 'date': '20261117' is not a date"),
        (("date: 2026-11-17", "date: 2026-11-16"), "key 'date': 2026-11-16 differs from the"),
        (("type: added\n", ""), "key 'type' is missing or empty"),
        (("impact: high\n", ""), "key 'impact' is missing or empty"),
        (("date: 2026-11-17\n", ""), "key 'date' is missing or empty"),
        (("title: Reject a lot in quarantine with a signed record", "title:"), "key 'title' is"),
        (("title: Reject", "title: reject"), "key 'title': start with a capital letter"),
        (("signed record\n", "signed record.\n"), "key 'title': start with a capital letter"),
        (("pr: 44", "pr: #44"), "key 'pr': '#44' is not a pull request number"),
        (("link: quality:lot_list", "link: /lots/"), "key 'link': '/lots/' is not a URL name"),
        (("area: Lots", "area: " + "x" * 41), "key 'area': 1-40 characters"),
        (("pr: 44", "pr: 44\npr: 45"), "key 'pr' appears twice"),
        (("pr: 44", "pr: 44\nversion: 2"), "key 'version' is unknown"),
        (("pr: 44", "pr: 44\nnot a pair"), "front matter line is not 'key: value'"),
        (("A quality person rejects a lot with a **signature**.\n", ""), "the summary"),
        (("Migration", "### More\nMigration"), "the technical notes part has a heading"),
    ],
)
def test_an_invalid_entry_names_the_file_and_the_key(change, message):
    text = GOOD.replace(*change, 1)
    assert text != GOOD
    with pytest.raises(EntryError) as raised:
        parse_text(NAME, text)
    assert str(raised.value).startswith(f"changelog.d/{NAME}: ")
    assert message in str(raised.value)


@pytest.mark.parametrize(
    "name", ["reject.md", "2026-11-17.md", "2026-11-17-Reject.md", "2026-11-17-a_b.md", "x.txt"]
)
def test_the_file_name_is_date_and_slug(name):
    with pytest.raises(EntryError, match="file name must be YYYY-MM-DD-short-slug.md"):
        parse_text(name, GOOD)


def test_an_entry_without_front_matter_is_refused():
    with pytest.raises(EntryError, match="missing the front matter"):
        parse_text(NAME, "date: 2026-11-17\n")


def test_load_reads_every_valid_file_and_reports_each_bad_one(tmp_path):
    (tmp_path / NAME).write_text(GOOD)
    (tmp_path / "2026-11-18-bad.md").write_text(
        GOOD.replace("2026-11-17", "2026-11-18").replace("impact: high", "impact: big")
    )
    (tmp_path / "notes.txt").write_text("ignored")
    found, errors = load(tmp_path)
    assert [e.id for e in found] == ["2026-11-17-reject-a-lot"]
    assert errors == [
        "changelog.d/2026-11-18-bad.md: key 'impact': 'big' is not one of high, medium, low"
    ]
    assert load(tmp_path / "missing") == ([], [])


def test_order_is_newest_first_then_by_title():
    items = [
        entry("2026-11-10", "older"),
        entry("2026-11-17", "zeta", title="Zeta change"),
        entry("2026-11-17", "alpha", title="alpha change"),
        entry("2026-11-12", "middle"),
    ]
    assert [e.id for e in ordered(items)] == [
        "2026-11-17-alpha",
        "2026-11-17-zeta",
        "2026-11-12-middle",
        "2026-11-10-older",
    ]


def test_groups_are_months_with_their_date_range_and_impact_sections():
    items = [
        entry("2026-10-02", "october-low", "low"),
        entry("2026-11-17", "late-medium", "medium"),
        entry("2026-11-03", "early-high", "high"),
        entry("2026-11-09", "mid-low", "low"),
        entry("2026-12-01", "december", "high"),
    ]
    groups = grouped(items)
    assert [(g.label, g.range, g.anchor) for g in groups] == [
        ("December 2026", "2026-12-01", "2026-12"),
        ("November 2026", "2026-11-03 to 2026-11-17", "2026-11"),
        ("October 2026", "2026-10-02", "2026-10"),
    ]
    november = groups[1]
    assert [(s.impact, s.label, [e.id for e in s.entries]) for s in november.sections] == [
        ("high", "High impact", ["2026-11-03-early-high"]),
        ("medium", "Medium impact", ["2026-11-17-late-medium"]),
        ("low", "Low impact", ["2026-11-09-mid-low"]),
    ]
    assert november.count == 3
    assert [s.impact for s in groups[0].sections] == ["high"]  # empty sections are left out
    assert grouped([]) == []


def test_unread_counts_entries_newer_than_the_last_one_seen():
    items = [entry("2026-11-10", "a"), entry("2026-11-12", "b"), entry("2026-11-12", "c")]
    assert changelog.newest_id(items) == "2026-11-12-c"
    assert changelog.newest_id([]) == ""
    assert changelog.unread(items, "") == []  # no mark yet: nothing is new to a new reader
    assert [e.id for e in changelog.unread(items, "2026-11-10-a")] == [
        "2026-11-12-b",
        "2026-11-12-c",
    ]
    assert changelog.unread(items, "2026-11-12-c") == []
    # An entry that was removed still marks what was seen.
    assert [e.id for e in changelog.unread(items, "2026-11-11-gone")] == [
        "2026-11-12-b",
        "2026-11-12-c",
    ]


def test_the_changelog_lists_groups_impacts_and_entries_in_order():
    first = parse_text(NAME, GOOD)
    second = changelog.Entry(
        id="2026-10-05-a-fix",
        date=date(2026, 10, 5),
        type="fixed",
        impact="low",
        title="A fix",
        summary="Line one.\nLine two.",
    )
    text = render_changelog([second, first], link_label=lambda name: "Material lots")
    assert text.startswith(changelog.GENERATED_NOTE + "\n\n# Changelog\n")
    body = text.split("## ", 1)[1]
    assert body == dedent(
        """\
        November 2026 (2026-11-17)

        ### High impact

        - **Added**: Reject a lot in quarantine with a signed record · Lots · 2026-11-17 · [#44](https://github.com/openbga/qm-lims/pull/44)

          A quality person rejects a lot with a **signature**.

          In the application: **Material lots**

          > **Technical notes**
          >
          > Migration `quality.0012_lot_rejection`.

        ## October 2026 (2026-10-05)

        ### Low impact

        - **Fixed**: A fix · 2026-10-05

          Line one.
          Line two.
        """
    )


def test_an_empty_changelog_says_so():
    assert render_changelog([]).endswith("No changes are recorded yet.\n")
