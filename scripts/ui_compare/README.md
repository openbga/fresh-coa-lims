# UI before/after comparison

Screenshots of pages before and after a change, for pull-request review. "Before" is
`origin/develop`, served from a temporary worktree on 127.0.0.1:8013; "after" is your running
development server (default 127.0.0.1:8010). Both read the same synthetic records: the same
database by default, or a copy of it given with `--before-database-url`.

## Run

Start the development server with demo data (see CONTRIBUTING.md), then from the repository root:

```sh
set -a; . ./.env; set +a          # DATABASE_URL, DEMO_PASSWORD, …
uv run --group e2e python scripts/ui_compare/capture.py --list
uv run --group e2e python scripts/ui_compare/capture.py --pages lots,lot-released,demo_quality:/reports/
```

- `--pages`: ids from `--list`, a path such as `/lots/` (signed in as `demo_admin`), or
  `demo_quality:/path/` for any `demo_*` account. Without it, every listed page is captured.
  Each listed page has a desktop (1440×900) id and a phone (390×844) id ending in `-390`.
- `--after-only`: capture only the after side and reuse the existing before shots.
- `--after URL`: the after server (default `http://127.0.0.1:8010`).
- `--before-port`, `--before-tree`, `--keep-before`: where develop is served and checked out,
  and whether to keep the worktree for the next run.
- `--before-database-url`: a copy of the database for develop (`createdb -T`), needed when the
  branch has migrations develop's code cannot share a database with.

Record pages are found by state in the after database (`targets.py`): a released lot with an
issued certificate, a test awaiting review, an open investigation, an overdue stability pull, and
so on. A state the database does not hold is listed as a capture gap.

Each page is captured in light and dark, as the viewport and as a full page, with a pixel-difference
view and a horizontal-overflow measurement. The output goes to the ignored `.local/ui-compare/`:
open `index.html` there (the last line printed). The command exits non-zero if a page could not be
captured; `manifest.json` lists the gaps. Add hand-written notes in `.local/ui-compare/notes.json`
and rebuild the page with `python3 scripts/ui_compare/build.py`. Screenshots are never committed.
