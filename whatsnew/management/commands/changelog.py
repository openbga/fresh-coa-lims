"""Write CHANGELOG.md from changelog.d/, or check that the committed file is current.

uv run python manage.py changelog           # validate every entry and write CHANGELOG.md
uv run python manage.py changelog --check   # exit 1 if an entry is invalid or the file is stale
"""

import difflib
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from whatsnew import catalogue
from whatsnew import entries as changelog

STALE = """\
CHANGELOG.md is not what changelog.d/ generates. The file is generated: never edit it by hand.
- If your branch added or changed lines in CHANGELOG.md, move each change into an entry file in
  changelog.d/ (one file per change: the changelog-entry skill in .agents/skills/ and
  CONTRIBUTING.md, "Changelog entries"), and drop your edits to CHANGELOG.md.
- Then run `uv run python manage.py changelog` and commit CHANGELOG.md with the entry files.
- A rebase conflict in CHANGELOG.md: take either side, then regenerate the same way."""


def changelog_path() -> Path:
    return Path(getattr(settings, "CHANGELOG_PATH", settings.BASE_DIR / "CHANGELOG.md"))


def link_problems(entries):
    """One message per entry whose ``link`` is not a documented page reachable without arguments."""
    return [
        f"changelog.d/{e.id}.md: key 'link': {e.link!r} is not a documented page of the "
        "application that opens without arguments (see docs/pages/)"
        for e in entries
        if e.link and not catalogue.link_label(e.link)
    ]


class Command(BaseCommand):
    help = "Write CHANGELOG.md from the entries in changelog.d/ (--check: verify it is current)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Change nothing; exit 1 if an entry is invalid or CHANGELOG.md is stale.",
        )

    def handle(self, *args, check=False, **options):
        directory = catalogue.changelog_dir()
        entries, errors = changelog.load(directory)
        errors += link_problems(entries)
        if errors:
            raise CommandError("Invalid changelog entries:\n" + "\n".join(errors))
        text = changelog.render_changelog(entries, catalogue.link_label)
        path = changelog_path()
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        if check:
            if current != text:
                diff = list(
                    difflib.unified_diff(
                        text.splitlines(),
                        current.splitlines(),
                        "generated from changelog.d/",
                        "CHANGELOG.md",
                        lineterm="",
                        n=1,
                    )
                )
                shown = "\n".join(diff[:40]) + ("\n..." if len(diff) > 40 else "")
                raise CommandError(f"{STALE}\n\n{shown}")
            self.stdout.write(f"CHANGELOG.md is current ({len(entries)} entries).")
            return
        if current != text:
            path.write_text(text, encoding="utf-8")
            self.stdout.write(f"Wrote CHANGELOG.md ({len(entries)} entries).")
        else:
            self.stdout.write(f"CHANGELOG.md is already current ({len(entries)} entries).")
