"""The traceability map and the validation pack built from it (scripts/validation_pack.py)."""

import csv
import hashlib
import json
import shutil
import subprocess
import textwrap

import pytest

from scripts import validation_pack as pack

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_every_requirement_and_every_test_is_traced():
    """The repository's own map: a new requirement or a new test module must be traced."""
    assert pack.check() == []


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A small repository: two requirements, an application suite and a browser suite."""
    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setattr(pack, "_uncommitted", lambda root: False)
    root = tmp_path / "repo"
    write(
        root / "pyproject.toml",
        """
        [project]
        version = "0.2.0"
        [tool.pytest.ini_options]
        testpaths = ["app/tests"]
        """,
    )
    write(
        root / "docs/product.md",
        """
        ## Requirements and traceability

        | Product ID | Required outcome | Regulatory / policy basis | Delivery |
        |---|---|---|---|
        | OQ-002 | Audit <events> | REG-1 | Done |
        | OQ-001 | Rules & versions | REG-2 | Partly |

        Text after the table.
        """,
    )
    write(root / "docs/regulations.md", "# Regulations\n")
    write(
        root / "CHANGELOG.md",
        """
        # Changelog

        ## [Unreleased]

        - Something new.

        ## [0.1.0]

        - First.
        """,
    )
    write(
        root / "app/tests/test_rules.py",
        '''
        def test_version():
            """A version is approved by someone else.

            More detail."""


        class TestRetire:
            def test_retired(self):
                pass


        def helper():
            pass
        ''',
    )
    write(
        root / "app/tests/test_audit.py",
        '''
        def test_event():
            """<script>alert(1)</script> is shown as text."""
        ''',
    )
    write(root / "e2e/test_journey.py", "def test_journey():\n    pass\n")
    write(
        root / "docs/traceability.toml",
        """
        [requirements]
        "OQ-001" = ["app/tests/test_rules.py", "e2e/test_journey.py"]
        "OQ-002" = ["app/tests/test_audit.py::test_event"]
        [project]
        """,
    )
    return root


def results(root, suite, cases, suite_root="", commit=COMMIT, ran_on=COMMIT, changes="false"):
    """A results directory as the CI jobs write it: pytest records the commit it ran on in the
    JUnit file, and the environment step the commit after it."""
    directory = root.parent / "results" / suite
    directory.mkdir(parents=True)
    body = []
    for classname, name, outcome in cases:
        inner = {
            "passed": "",
            "failed": '<failure message="assert 1 == 2">trace</failure>',
            "error": '<error message="fixture broke">trace</error>',
            "skipped": '<skipped message="not here" type="pytest.skip"/>',
        }[outcome]
        body.append(
            f'<testcase classname="{classname}" name="{name}" time="0.5">{inner}</testcase>'
        )
    (directory / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + (
            f'<properties><property name="commit" value="{ran_on}"/>'
            f'<property name="uncommitted_changes" value="{changes}"/></properties>'
            if ran_on
            else ""
        )
        + "".join(body)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    (directory / "environment.json").write_text(
        json.dumps(
            {
                "suite": suite,
                "root": suite_root,
                "command": "pytest",
                "commit": commit,
                "uncommitted_changes": False,
                "run": "https://example.invalid/run/1",
                "runner": "Linux",
                "python": "3.14.0",
                "database": "PostgreSQL 17.6",
                "packages": {"Django": "5.2"},
            }
        ),
        encoding="utf-8",
    )
    return directory


APPLICATION = [
    ("app.tests.test_rules", "test_version", "passed"),
    ("app.tests.test_rules.TestRetire", "test_retired", "passed"),
    ("app.tests.test_audit", "test_event", "passed"),
]


def test_check_names_every_gap(repo):
    write(
        repo / "docs/traceability.toml",
        """
        [requirements]
        "OQ-001" = ["app/tests/test_rules.py::test_version", "app/tests/test_gone.py"]
        "OQ-003" = ["app/tests/test_audit.py::test_missing"]
        [project]
        """,
    )
    assert pack.check(repo) == [
        "OQ-002 has no test traced to it in docs/traceability.toml.",
        "docs/traceability.toml names OQ-003, which is not in docs/product.md.",
        "docs/traceability.toml names app/tests/test_audit.py::test_missing, which is not a test.",
        "docs/traceability.toml names app/tests/test_gone.py, which does not exist.",
        "app/tests/test_audit.py::test_event is not traced to a requirement in "
        "docs/traceability.toml.",
        "app/tests/test_rules.py::TestRetire::test_retired is not traced to a requirement in "
        "docs/traceability.toml.",
        "e2e/test_journey.py::test_journey is not traced to a requirement in "
        "docs/traceability.toml.",
    ]


def test_pack_of_passing_suites(repo):
    output = repo.parent / "pack"
    summary = pack.build(
        [
            results(repo, "application", APPLICATION),
            results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e"),
        ],
        output,
        repo,
    )
    assert summary["status"] == "passed"
    assert summary["commit"] == COMMIT and summary["version"] == "0.2.0"
    assert summary["release_notes"] == "[Unreleased]"
    assert [(r["id"], r["status"], r["counts"]) for r in summary["requirements"]] == [
        ("OQ-001", "passed", {"passed": 3, "failed": 0, "skipped": 0, "not_run": 0}),
        ("OQ-002", "passed", {"passed": 1, "failed": 0, "skipped": 0, "not_run": 0}),
    ]
    assert summary["untraced_results"] == []
    assert "packages" not in summary["suites"][0]["environment"]

    with (output / "traceability.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert {(r["requirement"], r["test"], r["suite"], r["outcome"]) for r in rows} == {
        ("OQ-001", "app/tests/test_rules.py::test_version", "application", "passed"),
        ("OQ-001", "app/tests/test_rules.py::TestRetire::test_retired", "application", "passed"),
        ("OQ-001", "e2e/test_journey.py::test_journey", "browser", "passed"),
        ("OQ-002", "app/tests/test_audit.py::test_event", "application", "passed"),
    }
    described = {r["test"]: r["description"] for r in rows}
    assert described["app/tests/test_rules.py::test_version"] == (
        "A version is approved by someone else."
    )
    with (output / "requirements.csv").open(encoding="utf-8") as handle:
        assert [r["requirement"] for r in csv.DictReader(handle)] == ["OQ-001", "OQ-002"]
    assert (output / "release-notes.md").read_text() == "## [Unreleased]\n\n- Something new.\n"
    assert (output / "results/browser/junit.xml").is_file()
    assert (output / "documents/traceability.toml").is_file()

    page = (output / "index.html").read_text()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>" not in page
    assert "Audit &lt;events&gt;" in page and "Rules &amp; versions" in page
    assert "does not validate the system" in page

    listed = {}
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ")
        listed[name] = digest
    files = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    assert set(listed) == files - {"SHA256SUMS"}
    for name, digest in listed.items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest


def test_release_notes_of_the_version_when_the_changelog_has_it(repo):
    text = (repo / "pyproject.toml").read_text().replace('"0.2.0"', '"0.1.0"')
    (repo / "pyproject.toml").write_text(text)
    assert pack.release_notes(repo, "0.1.0") == ("[0.1.0]", "## [0.1.0]\n\n- First.\n")


@pytest.mark.parametrize(
    ("outcome", "status", "requirement"),
    [
        ("failed", "failed", "failed"),
        ("error", "failed", "failed"),
        ("skipped", "incomplete", "not run"),
    ],
)
def test_a_failure_or_a_requirement_without_a_pass_fails_the_pack(
    repo, outcome, status, requirement
):
    cases = [*APPLICATION[:2], ("app.tests.test_audit", "test_event", outcome)]
    summary = pack.build(
        [
            results(repo, "application", cases),
            results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e"),
        ],
        repo.parent / "pack",
        repo,
    )
    assert summary["status"] == status
    assert summary["requirements"][1]["status"] == requirement
    if outcome != "skipped":
        with (repo.parent / "pack" / "traceability.csv").open(encoding="utf-8") as handle:
            row = next(r for r in csv.DictReader(handle) if r["requirement"] == "OQ-002")
        assert row["message"] in ("assert 1 == 2", "fixture broke")


def test_a_suite_that_did_not_run_leaves_the_pack_incomplete(repo):
    summary = pack.build([results(repo, "application", APPLICATION)], repo.parent / "pack", repo)
    assert summary["status"] == "incomplete"
    assert summary["requirements"][0]["counts"]["not_run"] == 1
    with (repo.parent / "pack" / "traceability.csv").open(encoding="utf-8") as handle:
        assert {
            "requirement": "OQ-001",
            "test": "e2e/test_journey.py::test_journey",
            "outcome": "not run",
        }.items() <= next(r for r in csv.DictReader(handle) if r["outcome"] == "not run").items()


def test_parametrized_and_untraced_results(repo):
    cases = [
        ("app.tests.test_rules", "test_version[a]", "passed"),
        ("app.tests.test_rules", "test_version[b]", "passed"),
        *APPLICATION[1:],
        ("app.tests.test_other", "test_unknown", "passed"),
    ]
    summary = pack.build(
        [
            results(repo, "application", cases),
            results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e"),
        ],
        repo.parent / "pack",
        repo,
    )
    assert summary["requirements"][0]["counts"]["passed"] == 4
    assert summary["untraced_results"] == ["app.tests.test_other::test_unknown"]
    assert summary["status"] == "incomplete"


def test_refuses_results_of_another_commit_or_mixed_commits(repo, monkeypatch):
    application = results(repo, "application", APPLICATION)
    browser = results(
        repo, "browser", [("test_journey", "test_journey", "passed")], "e2e", "f" * 40, "f" * 40
    )
    with pytest.raises(pack.PackError, match="different commits"):
        pack.build([application, browser], repo.parent / "pack", repo)
    monkeypatch.setenv("GITHUB_SHA", "e" * 40)
    with pytest.raises(pack.PackError, match="but the pack is built at"):
        pack.build([application], repo.parent / "pack", repo)
    assert not (repo.parent / "pack").exists()


def test_refuses_an_incomplete_map_a_repeated_suite_and_an_existing_directory(repo):
    application = results(repo, "application", APPLICATION)
    with pytest.raises(pack.PackError, match="given twice"):
        pack.build([application, application], repo.parent / "pack", repo)
    existing = repo.parent / "existing"
    existing.mkdir()
    with pytest.raises(pack.PackError, match="already exists"):
        pack.build([application], existing, repo)
    (repo / "docs/traceability.toml").write_text('[requirements]\n"OQ-001" = ["app/tests/"]\n')
    with pytest.raises(pack.PackError, match="OQ-002 has no test traced"):
        pack.build([application], repo.parent / "pack", repo)
    shutil.rmtree(application)
    application.mkdir()
    with pytest.raises(pack.PackError, match="junit.xml|environment.json"):
        pack.read_results(application, repo)


def test_command_line_exit_status(repo, monkeypatch, capsys):
    monkeypatch.setattr(pack, "ROOT", repo)
    application = results(repo, "application", APPLICATION)
    browser = results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e")
    output = repo.parent / "pack"
    assert pack.main(["check"]) == 0
    assert pack.main(["build", "--results", str(application), "--output", str(output)]) == 1
    err = capsys.readouterr().err
    assert "Requirements not passed: OQ-001 (incomplete)" in err
    assert "Not run: e2e/test_journey.py::test_journey" in err
    assert json.loads((output / "pack.json").read_text())["not_run"] == [
        "e2e/test_journey.py::test_journey"
    ]
    shutil.rmtree(output)
    argv = ["build", "--results", str(application), "--results", str(browser)]
    assert pack.main([*argv, "--output", str(output)]) == 0
    assert pack.main([*argv, "--output", str(output)]) == 2
    assert "already exists" in capsys.readouterr().err


def test_uncommitted_changes_leave_the_pack_incomplete(repo, monkeypatch):
    application = results(repo, "application", APPLICATION)
    browser = results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e")
    environment = json.loads((browser / "environment.json").read_text())
    environment["uncommitted_changes"] = True
    (browser / "environment.json").write_text(json.dumps(environment))
    summary = pack.build([application, browser], repo.parent / "tested", repo)
    assert (summary["status"], summary["uncommitted_changes"]) == ("incomplete", True)
    assert "not those of the commit named" in (repo.parent / "tested" / "index.html").read_text()

    environment["uncommitted_changes"] = False
    (browser / "environment.json").write_text(json.dumps(environment))
    monkeypatch.setattr(pack, "_uncommitted", lambda root: True)
    summary = pack.build([application, browser], repo.parent / "built", repo)
    assert (summary["status"], summary["uncommitted_changes"]) == ("incomplete", True)


def test_uncommitted_changes_are_read_from_git(tmp_path):
    assert pack._uncommitted(tmp_path)  # not a checkout at all

    def git(*args):
        identity = ["-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid"]
        subprocess.run(["git", *identity, *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "a.txt").write_text("one")
    git("add", "a.txt")
    git("commit", "-q", "-m", "synthetic")
    assert not pack._uncommitted(tmp_path)
    (tmp_path / "a.txt").write_text("two")
    assert pack._uncommitted(tmp_path)
    git("checkout", "-q", "a.txt")
    (tmp_path / "new.py").write_text("")
    assert pack._uncommitted(tmp_path)


def test_results_must_record_the_commit_their_tests_ran_on(repo):
    browser = [("test_journey", "test_journey", "passed")]
    with pytest.raises(pack.PackError, match="does not record the commit"):
        pack.read_results(results(repo, "application", APPLICATION, ran_on=None), repo)
    later = results(repo, "browser", browser, "e2e", ran_on="d" * 40)
    with pytest.raises(pack.PackError, match="the tests ran on d+, but the environment"):
        pack.read_results(later, repo)


def test_tests_run_on_uncommitted_changes_leave_the_pack_incomplete(repo):
    summary = pack.build(
        [
            results(repo, "application", APPLICATION, changes="true"),
            results(repo, "browser", [("test_journey", "test_journey", "passed")], "e2e"),
        ],
        repo.parent / "pack",
        repo,
    )
    assert (summary["status"], summary["uncommitted_changes"]) == ("incomplete", True)


def test_a_skip_needs_a_reason_in_the_map(repo):
    cases = [APPLICATION[1], APPLICATION[2], ("app.tests.test_rules", "test_version", "skipped")]
    browser = [("test_journey", "test_journey", "passed")]
    summary = pack.build(
        [results(repo, "application", cases), results(repo, "browser", browser, "e2e")],
        repo.parent / "unexplained",
        repo,
    )
    assert summary["status"] == "incomplete"
    assert summary["requirements"][0]["status"] == "incomplete"
    assert summary["unexpected_skips"] == ["app/tests/test_rules.py::test_version"]

    with (repo / "docs/traceability.toml").open("a") as handle:
        handle.write('[skips]\n"app/tests/test_rules.py::test_version" = "Needs a <tool>."\n')
    summary = pack.build(
        [results(repo, "application2", cases), results(repo, "browser2", browser, "e2e")],
        repo.parent / "explained",
        repo,
    )
    assert summary["status"] == "passed"
    assert summary["allowed_skips"] == [
        {"test": "app/tests/test_rules.py::test_version", "reason": "Needs a <tool>."}
    ]
    assert "allowed: Needs a &lt;tool&gt;." in (repo.parent / "explained/index.html").read_text()


def test_nested_and_unittest_classes_must_be_traced(repo):
    write(
        repo / "app/tests/test_more.py",
        """
        import unittest


        class TestOuter:
            class TestInner:
                def test_inner(self):
                    pass


        class Checks(unittest.TestCase):
            def test_case(self):
                pass


        class Helper:
            def test_not_collected(self):
                pass
        """,
    )
    assert pack.check(repo) == [
        f"app/tests/test_more.py::{name} is not traced to a requirement in docs/traceability.toml."
        for name in ("TestOuter::TestInner::test_inner", "Checks::test_case")
    ]


def test_spreadsheet_formulas_are_kept_as_text():
    assert [pack._cell(v) for v in ("=1+1", "+x", "-x", "@x", "plain", 1.5)] == [
        "'=1+1",
        "'+x",
        "'-x",
        "'@x",
        "plain",
        1.5,
    ]


def test_record_checkout_writes_the_commit_into_the_junit_file(tmp_path, monkeypatch):
    from _pytest.junitxml import LogXML, xml_key

    monkeypatch.setenv("GITHUB_SHA", COMMIT)
    monkeypatch.setattr(pack, "_uncommitted", lambda root: False)
    junit = LogXML(str(tmp_path / "junit.xml"), None)
    config = type("Config", (), {"stash": pytest.Stash()})()
    pack.record_checkout(config)  # no JUnit file requested: nothing to do
    config.stash[xml_key] = junit
    pack.record_checkout(config)
    assert junit.global_properties == [("commit", COMMIT), ("uncommitted_changes", "false")]


def test_each_allowed_skip_names_one_test_and_a_reason(repo):
    with (repo / "docs/traceability.toml").open("a") as handle:
        handle.write(
            "[skips]\n"
            '"app/tests/" = "Everything may skip."\n'
            '"app/tests/test_audit.py::test_event" = " "\n'
            '"app/tests/test_rules.py::test_version" = true\n'
            '"app/tests/test_rules.py::test_gone" = "Gone."\n'
        )
    assert pack.check(repo) == [
        "docs/traceability.toml names app/tests/test_rules.py::test_gone, which is not a test.",
        "docs/traceability.toml allows skips of app/tests/; name each test that may skip.",
        "docs/traceability.toml allows a skip of app/tests/test_audit.py::test_event without a "
        "reason.",
        "docs/traceability.toml allows a skip of app/tests/test_rules.py::test_version without a "
        "reason.",
    ]


def test_outside_a_checkout_the_tests_run_and_the_build_refuses_them(tmp_path, monkeypatch):
    from _pytest.junitxml import LogXML, xml_key

    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setattr(pack, "ROOT", tmp_path)  # not a git checkout
    junit = LogXML(str(tmp_path / "junit.xml"), None)
    config = type("Config", (), {"stash": pytest.Stash()})()
    config.stash[xml_key] = junit
    pack.record_checkout(config)
    assert junit.global_properties == []
    with pytest.raises(pack.PackError, match="cannot be read"):
        pack._commit()
