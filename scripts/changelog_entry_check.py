"""Whether a pull request that changes the application adds an entry to changelog.d/.

Run by .github/workflows/changelog.yml on the pull request's merge commit:

    git diff --name-status --no-renames HEAD^1 HEAD | python3 scripts/changelog_entry_check.py

Exits 1 when a path outside NO_ENTRY_NEEDED changed and no file was added under changelog.d/.
A pull request with nothing users, deployers or integrators can observe that still trips this
check carries the label `no-changelog` and says why in its description. Standard library only.
"""

import sys
from fnmatch import fnmatch

# Paths nobody outside the code observes: tests, CI, agent instructions, internal documentation,
# the presentation website and the generated changelog. Everything else is application source,
# including settings, migrations, dependencies, the container image and deployment files.
NO_ENTRY_NEEDED = (
    "*.md",  # README, CONTRIBUTING, AGENTS, CHANGELOG (generated) and other root documents
    ".agents/*",
    ".claude/*",
    ".github/*",
    "changelog.d/*",
    "conftest.py",
    "docs/*",
    "e2e/*",
    "scripts/*",
    "tests/*",
    "*/tests/*",
    "website/*",
    "LICENSE",
    "NOTICE",
    ".gitignore",
)

MISSING = """\
This pull request changes the application but adds no entry to changelog.d/.

Add one file per change users, deployers or integrators can observe, for example
changelog.d/2026-11-17-short-slug.md, then run `uv run python manage.py changelog` and commit
CHANGELOG.md with it. How to write it: CONTRIBUTING.md, "Changelog entries".

If nothing in this pull request is observable outside the code, a maintainer adds the label
`no-changelog` and the description says why."""


def needs_no_entry(path):
    return any(fnmatch(path, pattern) for pattern in NO_ENTRY_NEEDED)


def verdict(lines):
    """``(ok, source_paths)`` for ``git diff --name-status`` output lines."""
    source, added_entry = [], False
    for line in lines:
        if not line.strip():
            continue
        status, _tab, path = line.rstrip("\n").partition("\t")
        if status.startswith("A") and fnmatch(path, "changelog.d/*.md") and "/" not in path[12:]:
            added_entry = True
        if not needs_no_entry(path):
            source.append(path)
    return (added_entry or not source), source


def main():
    ok, source = verdict(sys.stdin.read().splitlines())
    if ok:
        print("Changelog entry check passed.")
        return 0
    print(MISSING)
    print("\nApplication paths changed:\n" + "\n".join(f"  {path}" for path in source[:20]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
