---
name: changelog-entry
description: Write the changelog entry for an OpenBGA QM LIMS change (one file in changelog.d/, shown in the application under What's new and generated into CHANGELOG.md). Use for every change that users, deployers or integrators can observe, before committing or opening a pull request, and when a branch still carries hand edits to CHANGELOG.md.
---

# Changelog entry

Every change that users, deployers or integrators can observe adds one file to `changelog.d/` in
the same change. The application's **What's new** page (app `whatsnew`) and `CHANGELOG.md` are
built from those files; nobody keeps a second copy. `CHANGELOG.md` is generated: never edit it.

## When an entry is needed

| Change | Entry |
|---|---|
| A page, action, field, filter, rule, refusal, message, signature or audit effect people see | Yes |
| A setting, migration, dependency, container or deployment change, upgrade step, file or data format, audit action or evidence schema | Yes (a deployer or integrator observes it) |
| A security fix | Yes, `type: security`, `impact: high` |
| Refactors, tests, CI, agent instructions, internal docs, presentation website or roadmap only | No: say "No user-visible change" in the pull request; a maintainer labels it `no-changelog` if the check asks for an entry |

One entry per change people would describe separately. A pull request that ships two unrelated
changes has two entries; the technical side of a feature (its migration, settings, audit actions)
belongs in that feature's `## Technical notes`, not in an entry of its own.

## The file

`changelog.d/YYYY-MM-DD-short-slug.md`, dated the day you write it (lowercase letters, digits and
hyphens; the date in the name equals `date`):

```
---
date: 2026-11-17
type: added
impact: high
title: Reject a lot in quarantine with a signed record
area: Lots
link: quality:lot_list
pr: 44
---
One to three plain sentences for laboratory staff: what they can do now or what behaves
differently, and where to find it. Name on-screen labels in **bold**.

## Technical notes

Optional: migrations, settings, schema identifiers, audit actions, dependencies, upgrade steps.
```

| Key | Required | Value |
|---|---|---|
| `date` | yes | The day the change merges; for a new change, the day the entry is written |
| `type` | yes | `added`, `changed`, `fixed`, `removed`, `deprecated` or `security` ([Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)) |
| `impact` | yes | `high`, `medium` or `low` (next section) |
| `title` | yes | Sentence case, no trailing period, at most 120 characters, written for users |
| `area` | no | The sidebar label users know (Lots, Testing, Stability, Validation, Account access, ...), or `Sign-in`, `Page help`, `Whole application`, `Deployment` |
| `link` | no | A documented page that opens without arguments, as a URL name (`quality:lot_list`, `core:audit`); the page link is shown only to people whose roles show that page |
| `pr` | no | The pull request number, once known |

Flat `key: value` lines only. The summary is the text before `## Technical notes`; no other
headings. Inline markdown: `**bold**`, `` `code` ``, `[links](https://...)`; technical notes may
add paragraphs and one level of `-` bullets.

## Rate the impact

- **high**: a new capability or workflow; anything a user or deployer must act on (a required
  setting, a migration with upgrade steps, something now refused that was allowed); a change to
  how people work; a removal; a security fix.
- **medium**: a noticeable improvement to something that exists (a new filter, a clearer page,
  a faster or broader existing action).
- **low**: small fixes and polish.

Be honest: most changes are not high. When unsure between two, ask what a laboratory supervisor
would want to hear about first.

## Word it

- Plain language for laboratory staff, in the voice of the application's copy: calm and exact,
  no marketing ("easily", "powerful", "seamless"), no "we".
- Say what people can do now or what behaves differently, and where (the page and the label).
- Keep identifiers, settings and schema names for `## Technical notes`.
- Everything is public: synthetic examples only, no names of other products or vendors, no
  customer names, no compliance or validation claims, nothing about agents, worktrees or how the
  work was coordinated (AGENTS.md).

## Regenerate and check

```sh
uv run python manage.py changelog           # validates every entry, writes CHANGELOG.md
uv run python manage.py changelog --check   # CI: fails on an invalid entry or a stale file
```

Commit the entry file and `CHANGELOG.md` together. `whatsnew/tests` covers the parser and the
page; the `changelog` workflow fails a pull request that changes application source and adds no
file under `changelog.d/` (unless it carries the label `no-changelog`).

## A branch that still edits CHANGELOG.md by hand

Branches started before `changelog.d/` existed add bullets under `## [Unreleased]`. After
rebasing onto `develop`:

1. Copy your branch's bullets aside (`git diff develop... -- CHANGELOG.md` lists them). Resolve
   a conflict in `CHANGELOG.md` either way: step 3 regenerates the whole file.
2. Turn each bullet into an entry file as above: a plain summary on top, the bullet's technical
   text under `## Technical notes` so nothing is lost. Merge bullets that describe one change.
3. Run `uv run python manage.py changelog` and commit `changelog.d/` and `CHANGELOG.md`.

`manage.py changelog --check` prints these steps and a diff of the hand edits when it finds them.
