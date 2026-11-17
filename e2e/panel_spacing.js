() => {
  // Panel spacing (docs/ui-standards.md, "Panel spacing"): visible text and controls inside a panel sit at
  // least --vr-panel-inset from the panel's edge, stacked blocks in a panel body are at least
  // --vr-stack apart, and key facts start on their grid's track lines. Returns the offenders; an
  // empty list passes. Reused by qa on any page: page.evaluate(open("e2e/panel_spacing.js").read()).
  const root = getComputedStyle(document.documentElement);
  const rem = parseFloat(root.fontSize);
  const token = name => parseFloat(root.getPropertyValue(name)) * rem;
  const inset = token('--vr-panel-inset');
  const stack = token('--vr-stack');
  const tolerance = 1;
  const visible = el => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' &&
      !el.closest('.visually-hidden, .visually-hidden-focusable, [hidden], details:not([open]) > :not(summary)');
  };
  // The part of the page an element is actually shown in: clipped by scrolling ancestors.
  const shownIn = el => {
    let r = el.getBoundingClientRect();
    let box = {left: r.left, right: r.right, top: r.top, bottom: r.bottom};
    for (let a = el.parentElement; a; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) {
        const c = a.getBoundingClientRect();
        box = {left: Math.max(box.left, c.left), right: Math.min(box.right, c.right),
               top: Math.max(box.top, c.top), bottom: Math.min(box.bottom, c.bottom)};
      }
    }
    return box;
  };
  const label = el => {
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    return `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''} "${text.slice(0, 40)}"`;
  };
  const problems = [];
  let panels = 0;
  // A form page's form is a panel too (app.css, "Forms").
  for (const card of document.querySelectorAll('.card, .vr-main > .vr-form:not(:has(.card))')) {
    if (!visible(card) || card.closest('.modal:not(.show), .dropdown-menu:not(.show)')) continue;
    panels += 1;
    const c = card.getBoundingClientRect();
    // Text runs (measured as rendered glyph boxes) and controls.
    const boxes = [];
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.textContent.trim() && n.parentElement && visible(n.parentElement) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (r.width && r.height) boxes.push([n.parentElement, r]);
      }
    }
    for (const control of card.querySelectorAll('input:not([type=hidden]), select, textarea, button, .btn, .form-check-input, .ts-control')) {
      if (visible(control)) boxes.push([control, control.getBoundingClientRect()]);
    }
    for (const [el, r] of boxes) {
      const shown = shownIn(el);
      // Only what is actually visible: a box cut by a scrolling table is an overflow, not spacing.
      if (r.left < shown.left - 0.5 || r.right > shown.right + 0.5 || r.top < shown.top - 0.5 || r.bottom > shown.bottom + 0.5) continue;
      // Inside a table that scrolls sideways (an entry grid) any column may sit at the scroll edge.
      const scroller = el.closest('.vr-table-wrap');
      if (scroller && scroller.scrollWidth > scroller.clientWidth + 1) continue;
      const gap = Math.min(r.left - c.left, c.right - r.right);
      if (gap < inset - tolerance) {
        problems.push(`inset ${gap.toFixed(1)}px < ${inset}px: ${label(el)} in ${label(card).slice(0, 60)}`);
      }
    }
    // Stack: consecutive visible blocks in a panel body.
    for (const body of card.querySelectorAll('.vr-panel-body')) {
      if (!visible(body)) continue;
      const kids = [...body.children].filter(k => visible(k) && getComputedStyle(k).position !== 'absolute');
      for (let i = 1; i < kids.length; i++) {
        const gap = kids[i].getBoundingClientRect().top - kids[i - 1].getBoundingClientRect().bottom;
        // Blocks side by side on one line (a button and its note) are not a stack.
        if (gap < 0) continue;
        if (gap < stack - tolerance) {
          problems.push(`stack ${gap.toFixed(1)}px < ${stack}px: ${label(kids[i - 1]).slice(0, 50)} → ${label(kids[i]).slice(0, 50)}`);
        }
      }
    }
  }
  // Key facts (section 12): every fact starts on one of its grid's track lines, so labels and values
  // line up from row to row.
  for (const dl of document.querySelectorAll('dl.vr-facts')) {
    if (!visible(dl) || dl.closest('.alert')) continue;
    const style = getComputedStyle(dl);
    const tracks = style.gridTemplateColumns.split(' ').map(parseFloat);
    const gap = parseFloat(style.columnGap) || 0;
    const origin = dl.getBoundingClientRect().left + parseFloat(style.paddingLeft);
    const lines = tracks.map((_, i) => origin + tracks.slice(0, i).reduce((sum, w) => sum + w + gap, 0));
    for (const fact of dl.children) {
      if (!visible(fact)) continue;
      const left = fact.getBoundingClientRect().left;
      if (!lines.some(line => Math.abs(line - left) <= tolerance)) {
        problems.push(`fact off the grid at ${left.toFixed(1)}px: ${label(fact).slice(0, 60)}`);
      }
    }
  }
  // Tables: content is never cut off silently. A table wider than its panel must sit in a scroll
  // container (.vr-table-wrap); nothing may clip it, and no cell may clip its own content
  // (ellipsis text carries its full text in a tooltip and is not a cell clip).
  for (const table of document.querySelectorAll('.vr-main table')) {
    if (!visible(table)) continue;
    const t = table.getBoundingClientRect();
    let scroller = null, clipper = null;
    for (let a = table.parentElement; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (/(auto|scroll)/.test(s.overflowX)) { scroller = a; break; }
      if (/(hidden|clip)/.test(s.overflowX)) { clipper = a; break; }
    }
    const card = table.closest('.card');
    if (clipper && t.right > clipper.getBoundingClientRect().right + tolerance) {
      problems.push(`table clipped by ${label(clipper).slice(0, 40)}: ${Math.round(t.width)}px in ${Math.round(clipper.getBoundingClientRect().width)}px`);
    }
    if (!scroller && !clipper && card && t.right > card.getBoundingClientRect().right + tolerance) {
      problems.push(`table overflows its panel without scrolling: ${label(table).slice(0, 40)}`);
    }
    for (const cell of table.querySelectorAll('td, th')) {
      if (!visible(cell)) continue;
      if (/(hidden|clip)/.test(getComputedStyle(cell).overflowX) && cell.scrollWidth > cell.clientWidth + tolerance) {
        problems.push(`table cell clipped: "${cell.innerText.trim().slice(0, 40)}"`);
      }
    }
  }

  // From 1280px a table fits its panel: low- and medium-priority columns give way first, long text
  // wraps or truncates with a tooltip. Only an entry grid (a table of inputs) may scroll sideways.
  if (window.innerWidth >= 1280) {
    for (const wrap of document.querySelectorAll('.vr-main .vr-table-wrap')) {
      if (!visible(wrap) || wrap.querySelector('input:not([type=hidden]), select, textarea')) continue;
      if (wrap.scrollWidth > wrap.clientWidth + tolerance) {
        const heads = [...wrap.querySelectorAll('thead th')].map(th => `${th.textContent.trim()} ${Math.round(th.getBoundingClientRect().width)}`);
        problems.push(`table scrolls sideways at ${window.innerWidth}px (${wrap.scrollWidth}px in ${wrap.clientWidth}px): ${heads.join(', ').slice(0, 160)}`);
      }
    }
  }

  // Collapsible panels, closed: the head's title sits with the same inset above and below.
  for (const details of document.querySelectorAll('details.card')) {
    if (!visible(details)) continue;
    const wasOpen = details.open;
    details.open = false;
    const summary = details.querySelector(':scope > summary');
    const title = summary && summary.querySelector('.card-title');
    if (title) {
      const s = summary.getBoundingClientRect();
      const t = title.getBoundingClientRect();
      const above = t.top - s.top;
      const below = s.bottom - t.bottom;
      if (Math.abs(above - below) > tolerance) {
        problems.push(`closed panel head off-centre: ${above.toFixed(1)}px above, ${below.toFixed(1)}px below "${title.innerText.trim().slice(0, 40)}"`);
      }
    }
    details.open = wasOpen;
  }

  // Fact words (section "Key facts"): a fact's label or value never breaks inside a word. Only
  // identifiers, codes and hashes (.vr-id, .vr-data, code, Bootstrap's .text-break) may break
  // where they must.
  for (const dl of document.querySelectorAll('dl.vr-facts')) {
    if (!visible(dl)) continue;
    const walker = document.createTreeWalker(dl, NodeFilter.SHOW_TEXT, {
      acceptNode: n => n.textContent.trim() && n.parentElement && visible(n.parentElement) &&
        !n.parentElement.closest('.vr-id, .vr-data, code, .text-break, .visually-hidden') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
    });
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      for (const m of n.textContent.matchAll(/\S+/g)) {
        const range = document.createRange();
        range.setStart(n, m.index);
        range.setEnd(n, m.index + m[0].length);
        const lines = new Set([...range.getClientRects()].filter(r => r.width > 0).map(r => Math.round(r.top)));
        if (lines.size > 1) {
          problems.push(`word split across lines in facts: "${m[0].slice(0, 40)}" in ${label(n.parentElement).slice(0, 60)}`);
        }
      }
    }
  }
  return {inset, stack, panels, problems: [...new Set(problems)]};
}
