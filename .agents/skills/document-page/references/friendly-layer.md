# Writing page documentation: the friendly layer (full guide)

The summary of these rules is in the skill's `SKILL.md`; this file has the complete guide and its
examples. The examples come from `docs/pages/quality-lot-list.md` and
`docs/pages/quality-lot-detail.md`, the two reference pages.

The documentation panel has four parts. The first three are short; the fourth is the complete
reference, collapsed by default when the first three exist.

| Part | Where in the file | Reader's question | Length |
| --- | --- | --- | --- |
| What this page is for | front matter `summary:` | "Am I in the right place?" | 1–2 sentences, at most 240 characters, one line |
| Common tasks | `## Common tasks` | "How do I do the thing I came for?" | 2–5 tasks (`###` title of at most 80 characters), each a numbered list of 1–4 steps, each step at most 200 characters |
| Good to know | `## Good to know` | "What will surprise me or go wrong?" | 3–5 bullets, each at most 200 characters |
| All fields and actions | the seven reference sections | "What exactly does this field or rule do?" | Complete. `pagedocs/tests/test_coverage.py` still checks it |

The three friendly parts come together or not at all, and `## Common tasks` then `## Good to know`
come before `## Purpose`. `pagedocs/docs.py` refuses a file that breaks a limit or the order, so
the mistake shows when the tests run.

## Tone

- Write for a laboratory or quality person in the middle of their work. Use plain words, second
  person and the present tense: "Select [[Apply]]", not "The Apply control submits the filter".
- Say what something does for them, not how it is implemented. Leave out limits such as page
  sizes or character counts unless people hit them; those belong in the reference.
- One idea per sentence; avoid stacked parentheses. Sentence case.
- Use the QC terms the product uses: lot, sample, quarantine, specification, requirements,
  result, review, OOS, disposition, certificate of analysis. Never use internal names such as URL
  names, model fields or CSS classes.
- Never invent anything. Every sentence must be traceable to the reference or to the views,
  templates and models in the front matter (AGENTS.md rule 6). No policy, thresholds, compliance
  claims or features that don't exist. "QC disposition" never means manufacturer release.

## Summary

- Name the record or workflow and what the person can find or do here: "Every material lot in one
  list. Find a lot, see its status and open its record, or start a new lot in quarantine."
- Add who can use the page only when access is restricted: "Only the quality role can sign a
  disposition."
- Plain text only: no `[[ ]]` and no Markdown. The `## Purpose` section stays as the reference
  version.

## Common tasks

- 2–5 tasks, ordered by how often people do them. The first task is the page's main job.
- A task title is a verb phrase in the user's words: "Find a lot", "Release or reject the lot".
  It is not a control name, and it carries no `[[ ]]`.
- Each step is one action, written as one numbered line (an indented line continues it). Wrap
  every exact on-screen label in `[[ ]]`: `Select [[New material lot]].` The panel shows labels as
  quiet chips, so the reader can find the same words on the page. Copy labels character for
  character from the template or the shared component that renders them.
- Add an outcome only when it matters: "The new lot starts in Quarantine." Leave out keyboard
  details, validation messages and dialog mechanics; the reference covers them.
- A task may end on another page ("Select [[Review disposition]] ... Sign with your PIN on that
  page") when this page is where people start it. Take the wording from that page's doc.
- Leave out tasks that no role can perform on this page. When a task needs a role or a state,
  say so in the step: "It shows only while the lot is in Quarantine."

## Good to know

Include something only if it:

- regularly surprises people: "The newest lot record comes first, not the lot received most
  recently.";
- prevents a wrong conclusion: "A discrepancy found on receipt does not hold the lot.";
- explains a block or refusal: "You cannot release or reject a lot that holds your own receipt,
  supplier certificate, sampling or test data, even with the quality role."; or
- protects the record: "A correction adds a linked record and the earlier one stays."

Leave everything else in the reference: default page sizes, sort tie-breakers, character limits,
dialog buttons, column lists and anything that reads like a test assertion. If you have more than
five, the page probably needs a better task instead.

## The reference ("All fields and actions")

- Keep the seven sections complete and verified (`SKILL.md`, "Find the logic" and "Accuracy
  rules"). With the friendly layer each section renders collapsed, with a "Find a field or action"
  filter above them, so readers reach it by searching, not by reading top to bottom.
- Don't repeat tasks or "Good to know" items word for word. The reference states the rule fully;
  the friendly layer says why it matters.
- When a label changes, change it in both places in the same change.

## Checklist for each page

- [ ] `summary`: 1–2 sentences on one line, at most 240 characters, no implementation detail.
- [ ] `## Common tasks`: 2–5 verb-phrase titles, 1–4 numbered steps each, exact labels in `[[ ]]`.
- [ ] `## Good to know`: 3–5 bullets, each surprising, preventive, explaining a block or
      protecting the record.
- [ ] Both sections come before `## Purpose`; the seven reference sections are unchanged.
- [ ] Every sentence is traceable to the reference or the source in the front matter.
- [ ] `reviewed` is today's date.
- [ ] Read it in the panel beside the page: every `[[label]]` exists on that page (or on the
      page the task names), in the state the step describes.
