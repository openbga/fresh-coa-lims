"""The pull-request check asking for an entry in changelog.d/ (.github/workflows/changelog.yml)."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "changelog_entry_check", ROOT / "scripts" / "changelog_entry_check.py"
)
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


@pytest.mark.parametrize(
    ("diff", "ok"),
    [
        (["M\tquality/views.py"], False),
        (["M\tquality/views.py", "A\tchangelog.d/2026-11-17-lot-filter.md"], True),
        (["M\tquality/views.py", "M\tchangelog.d/2026-11-10-older.md"], False),
        (["A\tquality/migrations/0013_x.py", "M\tCHANGELOG.md"], False),
        (["M\tuv.lock", "M\tpyproject.toml"], False),
        (["M\tDockerfile"], False),
        (["M\ttemplates/includes/app_footer.html"], False),
        (["M\tquality/tests/test_lots.py", "M\te2e/test_journey.py", "M\tconftest.py"], True),
        (["M\t.github/workflows/checks.yml", "A\t.agents/skills/x/SKILL.md"], True),
        (["M\tdocs/operations.md", "M\tREADME.md", "M\twebsite/roadmap.html"], True),
        (["M\tchangelog.d/2026-11-10-older.md", "M\tCHANGELOG.md"], True),
        (["A\tchangelog.d/nested/2026-11-17-x.md", "M\tquality/views.py"], False),
        ([], True),
    ],
)
def test_application_changes_need_an_added_entry(diff, ok):
    assert check.verdict(diff)[0] is ok


def test_the_failure_says_what_to_do(capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("M\tquality/views.py\n"))
    assert check.main() == 1
    out = capsys.readouterr().out
    assert "adds no entry to changelog.d/" in out
    assert "uv run python manage.py changelog" in out
    assert "no-changelog" in out
    assert "  quality/views.py" in out
