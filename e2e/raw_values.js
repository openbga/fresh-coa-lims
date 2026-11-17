(usernames = []) => {
  // Raw machine values in the visible text of <main> (e2e/test_raw_values.py): a Python repr of a
  // dict, list, Decimal or model object, a bare True/False, an unformatted ISO timestamp, or a raw
  // audit action code shown as a history title or table cell. Returns the offenders; an empty list
  // passes. The English word "None" is a deliberate value in some facts and is not flagged.
  // Adapted from qa's scanner (.local/qa/raw.js).
  const hits = [];
  const visible = el => {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const where = el => {
    // Field label: the nearest th (same column), dt, label or panel heading.
    const cell = el.closest('td, dd, li, p, div');
    let label = '';
    const td = el.closest('td');
    if (td) {
      const table = td.closest('table');
      const th = table && table.querySelectorAll('thead th')[td.cellIndex];
      label = th ? th.innerText.trim() : '';
    }
    const dd = el.closest('dd, .vr-fact-value, [class*=fact]');
    if (!label && dd) {
      const dt = dd.previousElementSibling || dd.parentElement.querySelector('dt, .vr-fact-label');
      label = dt ? dt.innerText.trim() : '';
    }
    const panel = el.closest('.card, section');
    const head = panel && panel.querySelector('h2, h3, .card-header, .vr-panel-title');
    const hook = el.closest('[class]');
    return `${head ? head.innerText.trim().split('\n')[0].slice(0, 40) : ''}${label ? ' › ' + label.slice(0, 30) : ''} [${hook ? hook.tagName.toLowerCase() + '.' + [...hook.classList].slice(0, 3).join('.') : ''}]`;
  };
  const patterns = [
    ['python-repr', /\{'[^']*':|\['[^']*'(,|\])|': \[|': '/],
    ['python-literal', /^(True|False)$/],
    ['decimal-repr', /Decimal\(/],
    ['iso-timestamp', /\d{4}-\d\d-\d\dT\d\d:\d\d|\d\d:\d\d:\d\d\.\d{1,6}|[+-]\d\d:\d\d\b(?! *[A-Za-z])|\d\d:\d\dZ\b/],
    ['object-repr', /<[A-Z]\w+: |object at 0x|\b[A-Z]\w+ object \(\d+\)/],
    ['model-label', /\b[a-z][a-z_]*\.[a-z][a-z_]* \d+\b/],
    // A stored choice or meaning shown as its code (account_authorized, not_completed); not a
    // username in brackets, an address, a file name or an identifier in code.
    ['snake-code', /(?<![(\w@/.-])[a-z]+_[a-z_]*[a-z](?![\w)@/.-])/],
  ];
  const root = document.querySelector('main') || document.body;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const t = n.textContent.trim();
    const el = n.parentElement;
    if (!t || !el || !visible(el) || el.closest('script, style, code.vr-allow-raw, textarea, pre.vr-raw-ok, .pagedocs-panel')) continue;
    const inCode = el.closest('code, kbd, .vr-code, .vr-id');
    for (const [name, re] of patterns) {
      if (name === 'snake-code' && inCode) continue;
      if (name === 'snake-code') {
        // Usernames are shown as they are (signed in as, actor); any other code is not.
        const codes = (t.match(new RegExp(re.source, 'g')) || []).filter(c => !usernames.includes(c));
        if (codes.length) hits.push({check: name, text: t.slice(0, 120), where: where(el)});
        continue;
      }
      if (re.test(t)) hits.push({check: name, text: t.slice(0, 120), where: where(el)});
    }
  }
  // Raw audit/action codes as history titles (e.g. "lot.received", "signature.denied").
  for (const title of root.querySelectorAll('.vr-timeline-title, .vr-history-item strong')) {
    const t = title.innerText.trim();
    if (/^[a-z_]+(\.[a-z_]+)+$/.test(t)) hits.push({check: 'audit-code', text: t, where: where(title)});
  }
  // Same in tables of audit pages (an Action column with raw codes).
  for (const td of root.querySelectorAll('td')) {
    const t = td.innerText.trim();
    if (/^[a-z_]+\.[a-z_]+(\.[a-z_]+)*$/.test(t) && !/@/.test(t)) hits.push({check: 'audit-code', text: t, where: where(td)});
  }
  return hits;
}
