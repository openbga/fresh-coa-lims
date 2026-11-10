from pagedocs.markdown import render


def test_raw_html_is_escaped():
    html = render('<script>alert(1)</script>\n\n<img src=x onerror="a()">')
    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_links_allow_only_relative_fragment_and_https():
    html = render(
        "[a](/lots/) [b](#x) [c](https://example.org) [d](javascript:alert(1)) [e](//evil)"
    )
    assert '<a href="/lots/">a</a>' in html
    assert '<a href="#x">b</a>' in html
    assert 'href="https://example.org" rel="noopener noreferrer"' in html
    assert 'href="javascript' not in html and 'href="//evil' not in html


def test_link_target_cannot_break_attribute():
    html = render('[x](/a"onmouseover="b)')
    assert "onmouseover=" not in html.replace("&quot;onmouseover=&quot;", "")


def test_headings_tables_lists_and_inline():
    html = render(
        "## Fields\n\n| Field | Model field |\n|---|---|\n| Number | `Lot.number` |\n\n"
        "- **Bold** and _italic_ in `lot_list`\n- second\n\n1. one\n2. two\n\n> Note text"
    )
    assert '<h3 id="pagedoc-fields">Fields</h3>' in html
    assert '<th scope="col">Model field</th>' in html and "<code>Lot.number</code>" in html
    assert "<li><strong>Bold</strong> and <em>italic</em> in <code>lot_list</code></li>" in html
    assert "<ol><li>one</li><li>two</li></ol>" in html
    assert 'class="pagedocs-note"' in html


def test_snake_case_is_not_italic():
    assert "<em>" not in render("created_at and lot_detail_view")


def test_duplicate_headings_get_unique_ids():
    html = render("## Rules\n\n## Rules")
    assert 'id="pagedoc-rules"' in html and 'id="pagedoc-rules-2"' in html
