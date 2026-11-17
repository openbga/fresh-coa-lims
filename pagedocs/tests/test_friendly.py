"""The friendly layer of page documentation: schema, limits, all-or-none, label chips, escaping."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string

from pagedocs.docs import parse
from pagedocs.markdown import label_text, render

FRONT = "---\ntitle: Synthetic page\nurls: quality:lot_list\nreviewed: 2026-11-17\n{extra}---\n"
REFERENCE = "".join(
    f"## {title}\n\n{title} text.\n\n"
    for title in (
        "Purpose",
        "Who can use it",
        "Layout",
        "Actions",
        "Fields",
        "Rules and hidden logic",
        "Related pages",
    )
)
SUMMARY = "summary: Find a synthetic record and see where it stands.\n"
TASKS = (
    "## Common tasks\n\n### Find a record\n\n1. Type in [[Find lot]].\n2. Select [[Search]].\n\n"
    "### Start a record\n\n1. Select [[New material lot]].\n\n"
)
TIPS = "## Good to know\n\n- First tip.\n- Second tip.\n- Third tip.\n\n"


def write(tmp_path, *, summary=SUMMARY, tasks=TASKS, tips=TIPS, reference=REFERENCE):
    path = tmp_path / "synthetic-page.md"
    path.write_text(FRONT.format(extra=summary) + tasks + tips + reference, encoding="utf-8")
    return path


def tasks_with(*tasks):
    body = "".join(
        f"### {title}\n\n" + "".join(f"{n}. {step}\n" for n, step in enumerate(steps, 1)) + "\n"
        for title, steps in tasks
    )
    return f"## Common tasks\n\n{body}"


def tips_with(*tips):
    return "## Good to know\n\n" + "".join(f"- {tip}\n" for tip in tips) + "\n"


def test_a_complete_layer_is_read(tmp_path):
    doc = parse(write(tmp_path))
    assert doc.summary == "Find a synthetic record and see where it stands."
    assert [task.title for task in doc.tasks] == ["Find a record", "Start a record"]
    assert doc.tasks[0].steps == ("Type in [[Find lot]].", "Select [[Search]].")
    assert doc.tips == ("First tip.", "Second tip.", "Third tip.")


def test_the_layer_is_optional(tmp_path):
    doc = parse(write(tmp_path, summary="", tasks="", tips=""))
    assert (doc.summary, doc.tasks, doc.tips) == ("", (), ())


@pytest.mark.parametrize(
    "missing",
    [
        {"summary": ""},
        {"tasks": ""},
        {"tips": ""},
        {"summary": "", "tasks": ""},
        {"tasks": "", "tips": ""},
    ],
)
def test_a_partial_layer_is_refused(tmp_path, missing):
    with pytest.raises(ImproperlyConfigured, match="all or none"):
        parse(write(tmp_path, **missing))


def test_the_layer_comes_before_the_reference(tmp_path):
    path = tmp_path / "synthetic-page.md"
    path.write_text(FRONT.format(extra=SUMMARY) + REFERENCE + TASKS + TIPS, encoding="utf-8")
    with pytest.raises(ImproperlyConfigured, match="before the reference"):
        parse(path)
    with pytest.raises(ImproperlyConfigured, match="before the reference"):
        parse(write(tmp_path, tasks=TIPS, tips=TASKS))


def test_continuation_lines_join_their_item(tmp_path):
    tasks = (
        "## Common tasks\n\n### Find a record\n\n1. Type the lot\n   number.\n\n"
        "### Other\n\n1. One.\n\n"
    )
    tips = "## Good to know\n\n- First\n  tip.\n- Second.\n- Third.\n\n"
    doc = parse(write(tmp_path, tasks=tasks, tips=tips))
    assert doc.tasks[0].steps == ("Type the lot number.",)
    assert doc.tips[0] == "First tip."


@pytest.mark.parametrize(
    ("tasks", "tips", "summary", "message"),
    [
        (tasks_with(("One", ["a"])), TIPS, SUMMARY, "2-5 tasks"),
        (tasks_with(*[(f"T{n}", ["a"]) for n in range(6)]), TIPS, SUMMARY, "2-5 tasks"),
        (tasks_with(("A" * 81, ["a"]), ("B", ["b"])), TIPS, SUMMARY, "title of 1-80"),
        (tasks_with(("[[A]]", ["a"]), ("B", ["b"])), TIPS, SUMMARY, "plain title"),
        (tasks_with(("A", []), ("B", ["b"])), TIPS, SUMMARY, "1-4 steps"),
        (tasks_with(("A", ["s"] * 5), ("B", ["b"])), TIPS, SUMMARY, "1-4 steps"),
        (tasks_with(("A", ["s" * 201]), ("B", ["b"])), TIPS, SUMMARY, "1-200 characters"),
        (TASKS, tips_with("a", "b"), SUMMARY, "3-5 items"),
        (TASKS, tips_with(*"abcdef"), SUMMARY, "3-5 items"),
        (TASKS, tips_with("t" * 201, "b", "c"), SUMMARY, "1-200 characters"),
        (TASKS, TIPS, f"summary: {'s' * 241}\n", "1-240 characters"),
        (TASKS, TIPS, "summary: \n", "1-240 characters"),
        (TASKS, TIPS, "summary: Select [[Search]].\n", "plain text"),
    ],
)
def test_limits(tmp_path, tasks, tips, summary, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        parse(write(tmp_path, tasks=tasks, tips=tips, summary=summary))


def test_the_limits_themselves_are_allowed(tmp_path):
    tasks = tasks_with(*[("A" * 80, ["s" * 200] * 4)] * 5)
    tips = tips_with(*["t" * 200] * 5)
    doc = parse(write(tmp_path, tasks=tasks, tips=tips, summary=f"summary: {'s' * 240}\n"))
    assert len(doc.tasks) == 5 and len(doc.tips) == 5


@pytest.mark.parametrize("text", ["Select [[Search.", "Select Search]].", "[[a [[b]] c]]", "[[]]"])
def test_label_markers_must_pair(tmp_path, text):
    with pytest.raises(ImproperlyConfigured, match=r"\[\[label\]\]"):
        parse(write(tmp_path, tips=tips_with(text, "b", "c")))


@pytest.mark.parametrize(
    "tasks",
    [
        "## Common tasks\n\nLoose paragraph.\n\n### A\n\n1. a\n\n### B\n\n1. b\n\n",
        "## Common tasks\n\n1. A step before any task.\n\n### A\n\n1. a\n\n### B\n\n1. b\n\n",
        "## Common tasks\n\n### A\n\n- a bullet\n\n### B\n\n1. b\n\n",
    ],
)
def test_common_tasks_hold_only_titles_and_steps(tmp_path, tasks):
    with pytest.raises(ImproperlyConfigured, match="only ### task titles"):
        parse(write(tmp_path, tasks=tasks))


def test_label_text_escapes_before_adding_chips():
    html = label_text('Select [[Save <b>now</b>]] then <script>alert("x")</script> & go.')
    assert html.count('<span class="pagedocs-label">') == 1
    assert '<span class="pagedocs-label">Save &lt;b&gt;now&lt;/b&gt;</span>' in html
    assert "<script" not in html and "<b>" not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; &amp; go." in html


def test_label_text_leaves_unpaired_brackets_as_typed():
    assert label_text("a [[b and c]] d [[e") == (
        'a <span class="pagedocs-label">b and c</span> d [[e'
    )


def test_the_shared_markdown_subset_has_no_chips():
    """The sign-in announcement uses render(): [[...]] stays literal text there."""
    assert "pagedocs-label" not in render("Select [[Search]].")


def test_reference_excludes_the_layer_and_keeps_anchors_unique(tmp_path):
    reference = REFERENCE.replace("Fields text.", "### Purpose\n\nA subheading.")
    doc = parse(write(tmp_path, reference=reference))
    assert [section.title for section in doc.reference][:2] == ["Purpose", "Who can use it"]
    assert "Common tasks" not in doc.html and "First tip" not in doc.html
    assert 'id="pagedoc-purpose"' in doc.html and 'id="pagedoc-purpose-2"' in doc.html


def test_template_with_the_layer(tmp_path):
    doc = parse(write(tmp_path, tips=tips_with("<script>x</script> [[Clear filters]]", "b", "c")))
    html = render_to_string("pagedocs/content.html", {"doc": doc, "url_name": "quality:lot_list"})
    assert "<script" not in html
    assert '<span class="pagedocs-label">Clear filters</span>' in html
    assert "data-pagedocs-summary" in html and "Find a synthetic record" in html
    assert html.count("data-pagedocs-section") == 7 and "<details" in html
    assert "<details" in html and " open" not in html.split("data-pagedocs-reference", 1)[1]
    assert "data-pagedocs-filter-box hidden" in html  # revealed by pagedocs.js


def test_template_without_the_layer_renders_the_reference_open(tmp_path):
    doc = parse(write(tmp_path, summary="", tasks="", tips=""))
    html = render_to_string("pagedocs/content.html", {"doc": doc, "url_name": "quality:lot_list"})
    assert "<details" not in html and "data-pagedocs-filter" not in html
    assert '<h3 id="pagedoc-actions">Actions</h3>' in html
