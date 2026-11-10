"""A deliberately small, escape-first Markdown subset for page documentation.

Supported: ATX headings, paragraphs, ``-``/``*`` and ``1.`` lists (one level), pipe tables,
``>`` notes, fenced code, ``---`` rules, and inline ``code``, **bold**, *italic*/_italic_ and
[links](target). Raw HTML is never passed through: every character is escaped before inline
markup is applied, and link targets are limited to relative paths, fragments and https.
"""

import re
from html import escape

from django.utils.safestring import SafeString, mark_safe
from django.utils.text import slugify

_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")
_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])[*_](?![\s*_])(.+?)(?<![\s*_])[*_](?![\w*])")
_SAFE_TARGET = re.compile(r"^(/(?!/)|#|https://)[^\"'<>\s]*$")


def _inline(text):
    """Escape text, then apply inline markup to the escaped form."""
    spans = []

    def stash(html):
        spans.append(html)
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE_SPAN.sub(lambda m: stash(f"<code>{escape(m.group(1))}</code>"), text)

    def link(match):
        label, target = match.group(1), match.group(2)
        if not _SAFE_TARGET.match(target):
            return stash(escape(label))
        external = target.startswith("https://")
        rel = ' rel="noopener noreferrer" target="_blank"' if external else ""
        return stash(f'<a href="{escape(target)}"{rel}>{_emphasis(escape(label))}</a>')

    text = _LINK.sub(link, text)
    text = _emphasis(escape(text, quote=False))
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def _emphasis(text):
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    return _ITALIC.sub(r"<em>\1</em>", text)


def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", line)]


def render(source: str, heading_offset: int = 1) -> SafeString:
    """Render ``source`` to sanitized HTML. Headings shift by ``heading_offset`` levels."""
    lines = source.replace("\r\n", "\n").split("\n")
    out, paragraph, used_ids = [], [], set()
    i = 0

    def flush():
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush()
            i += 1
            continue
        if stripped.startswith("```"):
            flush()
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            out.append(f"<pre><code>{escape(chr(10).join(body))}</code></pre>")
            i += 1
            continue
        if heading := _HEADING.match(stripped):
            flush()
            level = min(len(heading.group(1)) + heading_offset, 6)
            text = heading.group(2)
            base = "pagedoc-" + (slugify(text) or "section")
            anchor, n = base, 2
            while anchor in used_ids:
                anchor, n = f"{base}-{n}", n + 1
            used_ids.add(anchor)
            out.append(f'<h{level} id="{anchor}">{_inline(text)}</h{level}>')
            i += 1
            continue
        if re.fullmatch(r"-{3,}|\*{3,}", stripped):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if (
            stripped.startswith("|")
            and i + 1 < len(lines)
            and _TABLE_RULE.match(lines[i + 1].strip())
        ):
            flush()
            head = _cells(stripped)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            th = "".join(f'<th scope="col">{_inline(c)}</th>' for c in head)
            body = "".join(
                "<tr>"
                + "".join(f"<td>{_inline(c)}</td>" for c in (row + [""] * len(head))[: len(head)])
                + "</tr>"
                for row in rows
            )
            out.append(
                '<div class="table-responsive"><table class="table table-sm pagedocs-table">'
                f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"
            )
            continue
        if stripped.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f'<div class="pagedocs-note"><p>{_inline(" ".join(quote))}</p></div>')
            continue
        bullet, ordered = _BULLET.match(line), _ORDERED.match(line)
        if bullet or ordered:
            flush()
            pattern, tag = (_BULLET, "ul") if bullet else (_ORDERED, "ol")
            items = []
            while i < len(lines):
                match = pattern.match(lines[i])
                if match:
                    items.append(match.group(1))
                elif lines[i].startswith(("  ", "\t")) and lines[i].strip() and items:
                    items[-1] += " " + lines[i].strip()  # continuation line
                else:
                    break
                i += 1
            lis = "".join(f"<li>{_inline(item)}</li>" for item in items)
            out.append(f"<{tag}>{lis}</{tag}>")
            continue
        paragraph.append(stripped)
        i += 1
    flush()
    return mark_safe("\n".join(out))  # noqa: S308 - every fragment above is escaped
