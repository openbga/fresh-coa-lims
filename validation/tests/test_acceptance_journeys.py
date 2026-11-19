"""The acceptance journeys command: it runs only in a database created for it, every journey
passes on this release, a broken control is reported as a failed step, and the evidence it
writes checks out and holds no credential."""

import hashlib
import io
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection

from analytical import services as analytical
from quality.models import Lot
from validation import acceptance
from validation.management.commands import acceptance_journeys

pytestmark = pytest.mark.django_db(transaction=True)


def run(tmp_path, name="run", **options):
    out = io.StringIO()
    call_command(
        "acceptance_journeys",
        database_name=options.get("database", connection.settings_dict["NAME"]),
        output=str(tmp_path / name),
        operator=options.get("operator", "Synthetic operator"),
        stdout=out,
    )
    return tmp_path / name, out.getvalue()


def sums_check(folder):
    """sha256sum -c SHA256SUMS, in Python: every listed file matches and every file is listed."""
    listed = {}
    for line in (folder / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        listed[path] = digest
    present = {
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS"
    }
    assert set(listed) == present
    for path, digest in listed.items():
        assert hashlib.sha256((folder / path).read_bytes()).hexdigest() == digest, path


@pytest.fixture
def captured_secrets(monkeypatch):
    """Every password and PIN the run generates, to look for them in what it writes."""
    seen = []
    original = acceptance.AcceptanceRun._credentials

    def credentials(self):
        password, pin = original(self)
        seen.extend([password, pin])
        return password, pin

    monkeypatch.setattr(acceptance.AcceptanceRun, "_credentials", credentials)
    return seen


def test_every_journey_passes_and_its_evidence_checks_out(tmp_path, captured_secrets, monkeypatch):
    monkeypatch.setenv("SOURCE_REVISION", "0123456789abcdef0123456789abcdef01234567")
    folder, stdout = run(tmp_path)

    report = json.loads((folder / "report.json").read_text())
    assert report["schema"] == acceptance.SCHEMA
    assert report["outcome"] == "passed"
    assert [j["key"] for j in report["journeys"]] == [
        "passing",
        "failing",
        "corrected",
        "rejected",
        "amended",
    ]
    steps = [s for j in [report["configuration"], *report["journeys"]] for s in j["steps"]]
    assert all(s["outcome"] == "passed" for s in steps), [
        s for s in steps if s["outcome"] != "passed"
    ]
    assert report["summary"]["steps"] == len(steps) == report["summary"]["steps_passed"]
    assert all(s["requirements"] and s["expected"] and s["observed"] for s in steps)
    assert report["run"]["operator"] == "Synthetic operator"
    assert report["environment"]["release"] == "0123456789abcdef0123456789abcdef01234567"
    assert report["environment"]["database"]["server_version"]
    assert "not a statement of compliance" in report["statement"]

    # Refusals are steps, and each was refused for its own reason.
    observed = {s["action"]: s["observed"] for s in steps}
    assert "review your own" in observed["The analyst reviews their own result"]
    assert "not accepted" in observed["The reviewer signs the review with a wrong PIN"]
    assert "no further retests" in observed["Quality authorizes a second retest"]
    assert (
        "also out of specification"
        in observed["Quality concludes that the original result is invalid"]
    )
    assert (
        "immutable"
        in observed["Read the certificate again and try to change its stored file in the database"]
    )

    # The lots stay as the journeys left them.
    states = dict(Lot.objects.values_list("number", "state"))
    assert sorted(states.values()) == [
        "cancelled",
        "rejected",
        "rejected",
        "released",
        "released",
        "released",
    ]

    # The folder's checksums, every lot record package and every certificate check out.
    sums_check(folder)
    packages = sorted(folder.rglob("*.zip"))
    assert len(packages) == 6
    for package in packages:
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            root = names[0].split("/")[0]
            sums = archive.read(f"{root}/SHA256SUMS").decode().splitlines()
            for line in sums:
                digest, path = line.split("  ", 1)
                assert hashlib.sha256(archive.read(f"{root}/{path}")).hexdigest() == digest
            assert f"{root}/record.pdf" in names and f"{root}/record.json" in names
    certificates = sorted(folder.rglob("*.pdf"))
    assert len(certificates) == 4  # passing, corrected, and the amended lot's two versions
    assert all(p.read_bytes().startswith(b"%PDF-") for p in certificates)
    for journey in report["journeys"]:
        for entry in journey["files"]:
            data = (folder / entry["path"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]

    html = (folder / "report.html").read_text()
    assert "The laboratory&#x27;s review" in html or "The laboratory's review" in html
    assert "Outcome: passed" in html

    # No password or PIN is shown or stored, in any file or package member, or in the output.
    assert len(captured_secrets) == 2 * len(acceptance.PEOPLE)
    texts = [stdout]
    for path in folder.rglob("*"):
        if path.suffix == ".zip":
            with zipfile.ZipFile(path) as archive:
                texts += [archive.read(n).decode("latin-1") for n in archive.namelist()]
        elif path.is_file():
            texts.append(path.read_bytes().decode("latin-1"))
    for secret in captured_secrets:
        assert not any(secret in text for text in texts)
    # Nor any stored hash of them.
    assert not any("pbkdf2_sha256$" in text for text in texts)
    assert "Acceptance journeys passed" in stdout


def test_a_broken_control_fails_its_step_and_the_run(tmp_path, monkeypatch):
    """Were self-review allowed, the journey reports it, stops, and the run exits non-zero;
    the other journeys still run and the report is written."""
    # The state and self-review predicate the signed review rechecks under lock.
    monkeypatch.setattr(analytical, "review_state_refusal", lambda actor, test: None)
    with pytest.raises(CommandError, match="Acceptance journeys failed"):
        run(tmp_path)
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    assert report["outcome"] == "failed"
    outcomes = {j["key"]: j["outcome"] for j in report["journeys"]}
    assert outcomes["passing"] == "failed"
    assert outcomes["rejected"] == "passed"
    failed = [s for j in report["journeys"] for s in j["steps"] if s["outcome"] == "failed"]
    assert failed[0]["action"] == "The analyst reviews their own result"
    assert failed[0]["observed"] == "The action was accepted."
    passing = report["journeys"][0]["steps"]
    assert passing[-1]["outcome"] == "failed"  # The journey stopped at the failed step.
    sums_check(tmp_path / "run")
    assert 'class="failed"' in (tmp_path / "run" / "report.html").read_text()


def test_a_failed_configuration_runs_no_journey(tmp_path, monkeypatch):
    def refused(**kwargs):
        raise ValidationError("synthetic configuration failure")

    monkeypatch.setattr(acceptance.catalog, "create_material", refused)
    with pytest.raises(CommandError, match="Acceptance journeys failed"):
        run(tmp_path)
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    assert report["configuration"]["outcome"] == "failed"
    assert report["configuration"]["steps"][-1]["observed"] == (
        "ValidationError: synthetic configuration failure"
    )
    assert {j["outcome"] for j in report["journeys"]} == {"not run"}
    assert not Lot.objects.exists()
    sums_check(tmp_path / "run")


def test_error_text_never_carries_a_stored_hash():
    stored = make_password("synthetic-secret-x9")
    text = acceptance.message_of(DatabaseError(f"Failing row contains (7, {stored}, 0)."))
    assert stored not in text and "Failing row contains" in text


def test_refuses_a_database_that_holds_any_account(tmp_path):
    get_user_model().objects.create_user(username="synthetic-existing", password="unused-x9!")
    with pytest.raises(CommandError, match="already holds accounts"):
        run(tmp_path)
    assert not (tmp_path / "run").exists()
    assert get_user_model().objects.count() == 1
    assert not Lot.objects.exists()


def test_refuses_a_database_other_than_the_one_named(tmp_path):
    """Forgetting to point DATABASE_URL at the new database never runs in the usual one."""
    with pytest.raises(CommandError, match="connected to the database"):
        run(tmp_path, database="qm_production")
    assert not (tmp_path / "run").exists()
    assert not get_user_model().objects.exists()


def test_refuses_an_existing_folder_or_no_operator(tmp_path):
    (tmp_path / "run").mkdir()
    with pytest.raises(CommandError, match="already exists"):
        run(tmp_path)
    with pytest.raises(CommandError, match="operator"):
        run(tmp_path, name="other", operator="   ")
    with pytest.raises(CommandError, match="does not exist"):
        run(tmp_path, name="missing/run")
    assert not get_user_model().objects.exists()


def test_refuses_a_database_not_migrated_to_this_release(tmp_path, monkeypatch):
    monkeypatch.setattr(
        acceptance_journeys.MigrationExecutor, "migration_plan", lambda self, targets: ["x"]
    )
    with pytest.raises(CommandError, match="migrations the database lacks"):
        run(tmp_path)
    assert not get_user_model().objects.exists()


def test_a_database_without_its_guard_is_reported_and_left_unchanged():
    group = Group.objects.create(name="synthetic-unguarded")
    Group.objects.create(name="synthetic-taken")
    probe = acceptance.AcceptanceRun(evidence=None, operator="Synthetic operator")
    with pytest.raises(acceptance.Mismatch, match="accepted the change"):
        probe.database_refuses(Group.objects.filter(pk=group.pk), name="changed")
    group.refresh_from_db()
    assert group.name == "synthetic-unguarded"
    # Another database error (here a unique constraint) is not a guard's refusal.
    with pytest.raises(acceptance.Mismatch, match="not by a guard"):
        probe.database_refuses(Group.objects.filter(pk=group.pk), name="synthetic-taken")
    group.refresh_from_db()
    assert group.name == "synthetic-unguarded"


def test_an_error_outside_any_step_fails_its_journey_and_the_report_is_written(
    tmp_path, monkeypatch
):
    def broken(self, journey):
        raise RuntimeError("synthetic failure outside a step")

    monkeypatch.setattr(acceptance.AcceptanceRun, "journey_rejected", broken)
    with pytest.raises(CommandError, match="Acceptance journeys failed"):
        run(tmp_path)
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    rejected = next(j for j in report["journeys"] if j["key"] == "rejected")
    assert rejected["outcome"] == "failed"
    assert rejected["steps"][-1]["observed"] == "RuntimeError: synthetic failure outside a step"
    assert next(j for j in report["journeys"] if j["key"] == "amended")["outcome"] == "passed"


def test_the_report_is_written_when_the_run_itself_is_interrupted(tmp_path, monkeypatch):
    def interrupted(self):
        self.current = self.setup
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(acceptance.AcceptanceRun, "run", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        run(tmp_path)
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    assert report["outcome"] == "failed"
    sums_check(tmp_path / "run")


def test_the_printed_report_escapes_what_it_shows():
    report = {
        "outcome": "passed",
        "statement": acceptance.STATEMENT,
        "summary": {"journeys": 0, "journeys_passed": 0, "steps": 0, "steps_passed": 0},
        "run": {
            "operator": "<script>alert(1)</script>",
            "started_at": "2026-11-17T00:00:00+00:00",
            "finished_at": "2026-11-17T00:01:00+00:00",
        },
        "environment": {
            "application": {"name": "OpenBGA QM LIMS", "version": "0"},
            "release": "abc",
            "database": {"engine": "PostgreSQL", "server_version": "17", "name": "x"},
            "python": "3",
            "django": "5",
            "platform": "p",
        },
        "people": [],
        "configuration": {
            "title": "t",
            "purpose": "p",
            "outcome": "passed",
            "lots": [],
            "files": [],
            "steps": [],
        },
        "journeys": [],
    }
    report["summary"]["steps_failed"] = 0
    page = acceptance.render_html(report)
    assert "<script>" not in page and "&lt;script&gt;" in page
