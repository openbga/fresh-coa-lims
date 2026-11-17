"""Build the validation pack of a release: the product requirements, the tests traced to each
one, their results with the environment they ran in, the release notes and a checksum of
every file.

The pack is supplier evidence for a laboratory's own risk-based validation. It does not
validate the system for anyone's intended use.

    python scripts/validation_pack.py check
        Check docs/traceability.toml against the requirements in docs/product.md and the
        test modules: every requirement traced, every test traced, every entry existing.
    python scripts/validation_pack.py environment --suite NAME --output FILE [--root DIR]
        Record, beside a suite's JUnit file, what the suite ran on (commit, Python, database
        server, installed packages and, with --browser, Chromium).
    python scripts/validation_pack.py build --results DIR [--results DIR ...]
            [--acceptance DIR] --output DIR
        Assemble the pack from result directories, each holding junit.xml and
        environment.json, and optionally the evidence folder of an acceptance journeys run
        (manage.py acceptance_journeys) on the same commit. Exits 1 unless every requirement
        and project check passed (a traced test passed, none failed, all ran, none skipped
        without a reason in the map), every result is traced, the checkout matched its commit
        and the acceptance journeys given passed.

Only the standard library is needed to check and build.
"""

import argparse
import ast
import csv
import hashlib
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "OpenBGA QM LIMS"
MAP = "docs/traceability.toml"
REQUIREMENTS = "docs/product.md"
BROWSER_SUITE = "e2e"
ACCEPTANCE_SCHEMA = "oq.acceptance-journeys/1"
STATEMENT = (
    "Supplier evidence for the laboratory's own risk-based validation. It shows which "
    "automated tests give evidence for each product requirement and how they ended on the "
    "commit named here, in the environment recorded with each suite. It does not validate "
    "the system for a laboratory's intended use, configuration or infrastructure, and it is "
    "not a statement of compliance with any regulation."
)


class PackError(Exception):
    """The pack cannot be built from these inputs."""


# Requirements and the traceability map


def read_requirements(root):
    """The rows of the "Requirements and traceability" table, in document order."""
    rows = []
    in_table = False
    for line in (root / REQUIREMENTS).read_text(encoding="utf-8").splitlines():
        if line.startswith("| Product ID |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows.append({"id": cells[0], "outcome": cells[1], "basis": cells[2], "delivery": cells[3]})
    if not rows:
        raise PackError(f"No requirements table in {REQUIREMENTS}.")
    return sorted(rows, key=lambda row: row["id"])


def read_map(root):
    data = tomllib.loads((root / MAP).read_text(encoding="utf-8"))
    return data.get("requirements", {}), data.get("project", {})


def test_roots(root):
    """The directories pytest collects: the application suite's test paths and the browser
    suite."""
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    paths = config["tool"]["pytest"]["ini_options"]["testpaths"]
    return [*paths, BROWSER_SUITE]


def discover_tests(root):
    """Every test function by node ID (path::name or path::Class::name) and the first
    paragraph of its docstring, read from the source without importing it."""
    tests = {}
    for directory in test_roots(root):
        for module in sorted((root / directory).rglob("test_*.py")):
            path = module.relative_to(root).as_posix()
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=path)
            _collect(tree.body, path, tests)
    return tests


def _collect(nodes, prefix, tests):
    """pytest's defaults: functions named test*, in modules or in classes named Test* (nested
    ones too) or derived from a unittest TestCase."""
    for node in nodes:
        if _is_test(node):
            tests[f"{prefix}::{node.name}"] = _summary(node)
        elif isinstance(node, ast.ClassDef) and (
            node.name.startswith("Test") or any(_is_test_case(base) for base in node.bases)
        ):
            _collect(node.body, f"{prefix}::{node.name}", tests)


def _is_test_case(base):
    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
    return name.endswith("TestCase")


def _is_test(node):
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def _summary(node):
    doc = ast.get_docstring(node) or ""
    return " ".join(doc.split("\n\n")[0].split())


def read_skips(root):
    """Tests that may be skipped where a pack is built, each with the reason."""
    return tomllib.loads((root / MAP).read_text(encoding="utf-8")).get("skips", {})


def _entries(traced, project):
    return [entry for group in (traced, project) for values in group.values() for entry in values]


def covers(entry, node_id):
    if entry.endswith("/"):
        return node_id.startswith(entry)
    return node_id == entry or node_id.startswith(entry + "::")


def check(root=None):
    """Problems with the traceability map, as sentences; empty when it is complete."""
    root = root or ROOT
    problems = []
    requirements = [row["id"] for row in read_requirements(root)]
    traced, project = read_map(root)
    tests = discover_tests(root)
    for requirement in requirements:
        if not traced.get(requirement):
            problems.append(f"{requirement} has no test traced to it in {MAP}.")
    for requirement in sorted(set(traced) - set(requirements)):
        problems.append(f"{MAP} names {requirement}, which is not in {REQUIREMENTS}.")
    skips = read_skips(root)
    entries = _entries(traced, project)
    for entry in sorted(set(entries) | set(skips)):
        path = entry.split("::")[0]
        if not (root / path).exists():
            problems.append(f"{MAP} names {entry}, which does not exist.")
        elif "::" in entry and not any(covers(entry, node_id) for node_id in tests):
            problems.append(f"{MAP} names {entry}, which is not a test.")
    for entry, reason in sorted(skips.items()):
        if "::" not in entry:
            problems.append(f"{MAP} allows skips of {entry}; name each test that may skip.")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{MAP} allows a skip of {entry} without a reason.")
    for node_id in tests:
        if not any(covers(entry, node_id) for entry in entries):
            problems.append(f"{node_id} is not traced to a requirement in {MAP}.")
    return problems


# Test environment


def environment(suite, root_dir, command, browser):
    """What a suite ran on. Run it in the job that ran the suite, after the tests."""
    from importlib import metadata

    record = {
        "suite": suite,
        "root": root_dir,
        "command": command,
        "recorded_at": _now(),
        "commit": _commit(),
        "uncommitted_changes": _uncommitted(ROOT),
        "ref": os.environ.get("GITHUB_REF", ""),
        "run": _run_url(),
        "runner": platform.platform(),
        "python": platform.python_version(),
        "database": _database_version(),
        "packages": dict(
            sorted(
                ((dist.metadata["Name"] or "?", dist.version) for dist in metadata.distributions()),
                key=lambda item: item[0].lower(),
            )
        ),
    }
    if browser:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch(headless=True)
            record["browser"] = f"Chromium {chromium.version}"
            chromium.close()
    return record


def _database_version():
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "not recorded: DATABASE_URL is not set"
    import psycopg

    # Only the server matters; the database named may not exist (pytest makes its own), so
    # fall back to the server's maintenance database.
    try:
        connection = psycopg.connect(url, connect_timeout=10)
    except psycopg.OperationalError:
        connection = psycopg.connect(url, dbname="postgres", connect_timeout=10)
    with connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
    return f"PostgreSQL {version}"


def _commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise PackError(f"The commit of {ROOT} cannot be read: {error}") from error
    return result.stdout.strip()


def _uncommitted(root):
    """Whether the checkout differs from its commit (or cannot be read as one)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return True
    return result.returncode != 0 or bool(result.stdout.strip())


def _run_url():
    server, repository, run = (
        os.environ.get(name, "")
        for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
    )
    if not (server and repository and run):
        return ""
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    return f"{server}/{repository}/actions/runs/{run}/attempts/{attempt}"


def _now():
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Results


def read_results(directory, root):
    """One suite's environment and its test cases, each with a node ID relative to the
    repository root."""
    directory = Path(directory)
    try:
        env = json.loads((directory / "environment.json").read_text(encoding="utf-8"))
        tree = ElementTree.parse(directory / "junit.xml")
    except (OSError, ValueError, ElementTree.ParseError) as error:
        raise PackError(f"{directory}: {error}") from error
    cases = []
    for case in tree.iter("testcase"):
        outcome = "passed"
        message = ""
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[child.tag]
                message = " ".join((child.get("message") or "").split())[:300]
                break
        cases.append(
            {
                "node": _node_id(case.get("classname", ""), case.get("name", ""), env, root),
                "outcome": outcome,
                "seconds": float(case.get("time") or 0),
                "message": message,
            }
        )
    if not cases:
        raise PackError(f"{directory / 'junit.xml'} holds no test case.")
    properties = {
        prop.get("name"): prop.get("value")
        for suite in tree.iter("testsuite")
        for prop in suite.findall("properties/property")
    }
    if "commit" not in properties:
        raise PackError(
            f"{directory / 'junit.xml'} does not record the commit its tests ran on; run the "
            "suite from a checkout of this repository, whose conftest records it."
        )
    if properties["commit"] != env.get("commit"):
        raise PackError(
            f"{directory}: the tests ran on {properties['commit']}, but the environment was "
            f"recorded at {env.get('commit')}."
        )
    env = {
        **env,
        "uncommitted_changes": env.get("uncommitted_changes", True)
        or properties.get("uncommitted_changes") != "false",
    }
    return env, cases


def record_checkout(config):
    """Write the commit and whether the checkout differs from it into the JUnit file as the
    tests start (called from each suite's conftest), so that results recorded later cannot be
    attributed to another commit."""
    from _pytest.junitxml import xml_key

    junit = config.stash.get(xml_key, None)
    if junit is None:
        return
    try:
        commit = _commit()
    except PackError:
        return  # outside a checkout: the build refuses these results, the tests still run
    junit.add_global_property("commit", commit)
    junit.add_global_property("uncommitted_changes", str(_uncommitted(ROOT)).lower())


def _node_id(classname, name, env, root):
    """pytest's JUnit class name is the module's dotted path from the suite's root directory,
    followed by any test classes."""
    parts = classname.split(".")
    base = root / env["root"] if env.get("root") else root
    for split in range(len(parts), 0, -1):
        module = base.joinpath(*parts[:split]).with_suffix(".py")
        if module.is_file():
            return "::".join([module.relative_to(root).as_posix(), *parts[split:], name])
    return "::".join([classname, name])


def _base(node):
    """The node ID without pytest's parameter suffix."""
    return re.sub(r"\[.*\]$", "", node)


# The pack


def read_acceptance(directory, commit):
    """The summary of an acceptance journeys run on `commit`, after checking every file of its
    folder against its SHA256SUMS."""
    directory = Path(directory)
    try:
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        sums = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError) as error:
        raise PackError(f"No acceptance journeys report in {directory}: {error}") from error
    if not isinstance(report, dict) or report.get("schema") != ACCEPTANCE_SCHEMA:
        raise PackError(f"{directory}/report.json is not an acceptance journeys report.")
    listed = {}
    for line in sums:
        digest, _, name = line.partition("  ")
        listed[name] = digest
    entries = list(directory.rglob("*"))
    odd = [p.relative_to(directory).as_posix() for p in entries if p.is_symlink()]
    odd += [
        p.relative_to(directory).as_posix()
        for p in entries
        if not p.is_symlink() and not p.is_dir() and not p.is_file()
    ]
    if odd:
        raise PackError(
            f"The acceptance evidence in {directory} holds links or special files: "
            + ", ".join(sorted(odd))
        )
    present = {p.relative_to(directory).as_posix() for p in entries if p.is_file()} - {"SHA256SUMS"}
    changed = sorted(
        name
        for name in present | set(listed)
        if name not in present
        or name not in listed
        or hashlib.sha256((directory / name).read_bytes()).hexdigest() != listed[name]
    )
    if changed:
        raise PackError(
            f"The acceptance evidence in {directory} does not match its SHA256SUMS: "
            + ", ".join(changed)
        )
    environment = report.get("environment") or {}
    if environment.get("release") != commit:
        raise PackError(
            f"The acceptance journeys ran on {environment.get('release')!r}, but the pack is "
            f"of {commit}."
        )
    return {
        "outcome": report.get("outcome"),
        "release": environment.get("release"),
        "summary": report.get("summary"),
        "run": report.get("run"),
        "environment": {
            key: environment.get(key) for key in ("database", "python", "django", "platform")
        },
        "journeys": [
            {"title": j.get("title"), "outcome": j.get("outcome")}
            for j in report.get("journeys", [])
        ],
    }


def build(results, output, root=None, acceptance=None):
    """Write the pack to `output` (which must not exist yet) and return its summary."""
    root = root or ROOT
    output = Path(output)
    if output.exists():
        raise PackError(f"{output} already exists; the pack is written to a new directory.")
    problems = check(root)
    if problems:
        raise PackError("The traceability map is incomplete:\n" + "\n".join(problems))
    suites = []
    for directory in results:
        env, cases = read_results(directory, root)
        suites.append({"directory": Path(directory), "environment": env, "cases": cases})
    names = [suite["environment"]["suite"] for suite in suites]
    if len(set(names)) != len(names):
        raise PackError(f"A suite is given twice: {', '.join(names)}.")
    commits = {suite["environment"]["commit"] for suite in suites}
    if len(commits) != 1:
        raise PackError(f"The results are of different commits: {', '.join(sorted(commits))}.")
    commit = commits.pop()
    if commit != _commit():
        raise PackError(f"The results are of {commit}, but the pack is built at {_commit()}.")
    journeys = read_acceptance(acceptance, commit) if acceptance else None

    requirements = read_requirements(root)
    traced, project = read_map(root)
    descriptions = discover_tests(root)
    rows = [
        {**case, "suite": suite["environment"]["suite"]}
        for suite in suites
        for case in suite["cases"]
    ]
    skips = read_skips(root)
    for row in rows:
        if row["outcome"] == "skipped":
            row["allowed"] = next(
                (reason for entry, reason in skips.items() if covers(entry, _base(row["node"]))),
                None,
            )
    groups = [(row["id"], row, traced[row["id"]]) for row in requirements]
    groups += [(name, None, entries) for name, entries in project.items()]
    evidence = []
    for key, row, entries in groups:
        matched = [r for r in rows if any(covers(entry, _base(r["node"])) for entry in entries)]
        ran = {_base(r["node"]) for r in matched}
        not_run = sorted(
            node
            for node in descriptions
            if node not in ran and any(covers(entry, node) for entry in entries)
        )
        evidence.append(
            {
                "id": key,
                "requirement": row,
                "entries": entries,
                "tests": matched,
                "not_run": not_run,
                "counts": _counts(matched, not_run),
                "status": _status(matched, not_run),
            }
        )
    entries = [entry for _, _, values in groups for entry in values]
    untraced = [r for r in rows if not any(covers(entry, _base(r["node"])) for entry in entries)]
    failed = [r for r in rows if r["outcome"] in ("failed", "error")]
    uncommitted = _uncommitted(root) or any(
        suite["environment"].get("uncommitted_changes", True) for suite in suites
    )
    unexpected_skips = [
        r["node"] for r in rows if r["outcome"] == "skipped" and not r.get("allowed")
    ]
    if failed or (journeys and journeys["outcome"] != "passed"):
        status = "failed"
    elif uncommitted or untraced or any(item["status"] != "passed" for item in evidence):
        status = "incomplete"
    else:
        status = "passed"
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    heading, notes = release_notes(root, version)
    summary = {
        "product": PRODUCT,
        "version": version,
        "commit": commit,
        "uncommitted_changes": uncommitted,
        "created_at": _now(),
        "status": status,
        "statement": STATEMENT,
        "release_notes": heading,
        "suites": [
            {
                "suite": suite["environment"]["suite"],
                "counts": _counts(suite["cases"], []),
                "environment": {
                    key: value for key, value in suite["environment"].items() if key != "packages"
                },
            }
            for suite in suites
        ],
        "requirements": [
            {
                "id": item["id"],
                "status": item["status"],
                "counts": item["counts"],
                "entries": item["entries"],
            }
            for item in evidence
            if item["requirement"]
        ],
        "project_checks": [
            {"name": item["id"], "status": item["status"], "counts": item["counts"]}
            for item in evidence
            if not item["requirement"]
        ],
        "untraced_results": [r["node"] for r in untraced],
        "failed_tests": [r["node"] for r in failed],
        "unexpected_skips": unexpected_skips,
        "allowed_skips": [
            {"test": r["node"], "reason": r["allowed"]} for r in rows if r.get("allowed")
        ],
        "not_run": sorted({node for item in evidence for node in item["not_run"]}),
        "acceptance": journeys,
    }

    output.mkdir(parents=True)
    for suite in suites:
        target = output / "results" / suite["environment"]["suite"]
        target.mkdir(parents=True)
        for name in ("junit.xml", "environment.json"):
            shutil.copyfile(suite["directory"] / name, target / name)
    if journeys:
        shutil.copytree(acceptance, output / "acceptance")
    documents = output / "documents"
    documents.mkdir()
    for source in (REQUIREMENTS, "docs/regulations.md", MAP):
        shutil.copyfile(root / source, documents / Path(source).name)
    (output / "release-notes.md").write_text(notes, encoding="utf-8")
    _write_csv(
        output / "requirements.csv",
        ["requirement", "required_outcome", "basis", "delivery", "status"] + list(_counts([], [])),
        [
            [item["id"], *(item["requirement"][k] for k in ("outcome", "basis", "delivery"))]
            + [item["status"], *item["counts"].values()]
            for item in evidence
            if item["requirement"]
        ],
    )
    _write_csv(
        output / "traceability.csv",
        ["requirement", "test", "suite", "outcome", "seconds", "description", "message"]
        + ["skip_allowed_because"],
        [
            [item["id"], r["node"], r["suite"], r["outcome"], f"{r['seconds']:.3f}"]
            + [descriptions.get(_base(r["node"]), ""), r["message"], r.get("allowed") or ""]
            for item in evidence
            for r in sorted(item["tests"], key=lambda r: r["node"])
        ]
        + [
            [item["id"], node, "", "not run", "", descriptions[node], "", ""]
            for item in evidence
            for node in item["not_run"]
        ],
    )
    (output / "pack.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(
        _html(summary, evidence, untraced, descriptions), encoding="utf-8"
    )
    _write_checksums(output)
    return summary


def release_notes(root, version):
    """The CHANGELOG section of this version, or the unreleased changes when it has none."""
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    for heading in (f"## [{version}]", "## [Unreleased]"):
        start = text.find(heading)
        if start == -1:
            continue
        end = text.find("\n## [", start + len(heading))
        section = text[start : end if end != -1 else len(text)].rstrip() + "\n"
        return heading[3:], section
    raise PackError("CHANGELOG.md has neither a section for this version nor [Unreleased].")


def _counts(cases, not_run):
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    for case in cases:
        counts["failed" if case["outcome"] == "error" else case["outcome"]] += 1
    counts["not_run"] = len(not_run)
    return counts


def _status(cases, not_run):
    """Failed when a test failed; not run without a passing test; incomplete while a traced
    test did not run or was skipped without a reason in the map."""
    if any(case["outcome"] in ("failed", "error") for case in cases):
        return "failed"
    if not any(case["outcome"] == "passed" for case in cases):
        return "not run"
    if not_run or any(case["outcome"] == "skipped" and not case.get("allowed") for case in cases):
        return "incomplete"
    return "passed"


def _write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows([_cell(value) for value in row] for row in rows)


def _cell(value):
    """Text a spreadsheet would read as a formula is kept as text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _write_checksums(output):
    lines = []
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(output).as_posix()}\n")
    (output / "SHA256SUMS").write_text("".join(lines), encoding="utf-8")


def _html(summary, evidence, untraced, descriptions):
    e = html.escape

    def counts(c):
        return (
            f"<td>{c['passed']}</td><td>{c['failed']}</td><td>{c['skipped']}</td>"
            f"<td>{c['not_run']}</td>"
        )

    def tests_table(item):
        rows = "".join(
            f"<tr><td><code>{e(r['node'])}</code><br><small>"
            f"{e(descriptions.get(_base(r['node']), ''))}</small></td><td>{e(r['suite'])}</td>"
            f"<td class='{e(r['outcome'])}'>{e(r['outcome'])}"
            f"{'<br><small>allowed: ' + e(r['allowed']) + '</small>' if r.get('allowed') else ''}"
            "</td>"
            f"<td>{e(r['message'])}</td></tr>"
            for r in sorted(item["tests"], key=lambda r: r["node"])
        )
        rows += "".join(
            f"<tr><td><code>{e(node)}</code></td><td></td><td class='not-run'>not run</td>"
            "<td></td></tr>"
            for node in item["not_run"]
        )
        return (
            "<table><thead><tr><th>Test</th><th>Suite</th><th>Outcome</th><th>Message</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )

    suites = "".join(
        f"<tr><td>{e(s['suite'])}</td>{counts(s['counts'])}"
        f"<td>Python {e(s['environment']['python'])}; {e(s['environment']['database'])}"
        f"{'; ' + e(s['environment']['browser']) if s['environment'].get('browser') else ''}"
        f"<br><small>{e(s['environment']['runner'])}</small></td>"
        f"<td><code>{e(s['environment']['command'])}</code>"
        f"{_link(s['environment'].get('run'))}</td></tr>"
        for s in summary["suites"]
    )
    requirement_rows = "".join(
        f"<tr><td><a href='#{e(item['id'])}'>{e(item['id'])}</a></td>"
        f"<td>{e(item['requirement']['outcome'])}</td>"
        f"<td class='{e(item['status'].replace(' ', '-'))}'>{e(item['status'])}</td>"
        f"{counts(item['counts'])}</tr>"
        for item in evidence
        if item["requirement"]
    )
    details = "".join(
        f"<section id='{e(item['id'])}'><h3>{e(item['id'])}: "
        f"{e(item['requirement']['outcome'] if item['requirement'] else 'project check')}</h3>"
        + (
            f"<p><strong>Basis:</strong> {e(item['requirement']['basis'])}</p>"
            f"<p><strong>Delivery:</strong> {e(item['requirement']['delivery'])}</p>"
            if item["requirement"]
            else ""
        )
        + f"<p><strong>Traced:</strong> {_codes(item['entries'])}</p>"
        f"<details><summary>{len(item['tests'])} results, {len(item['not_run'])} not run "
        f"({e(item['status'])})</summary>{tests_table(item)}</details></section>"
        for item in evidence
    )
    project_rows = "".join(
        f"<tr><td><a href='#{e(item['id'])}'>{e(item['id'])}</a></td>"
        f"<td class='{e(item['status'].replace(' ', '-'))}'>{e(item['status'])}</td>"
        f"{counts(item['counts'])}</tr>"
        for item in evidence
        if not item["requirement"]
    )
    untraced_list = (
        "<ul>" + "".join(f"<li><code>{e(r['node'])}</code></li>" for r in untraced) + "</ul>"
        if untraced
        else "<p>None.</p>"
    )
    skipped_list = (
        "<ul>"
        + "".join(
            f"<li><code>{e(item['test'])}</code>: allowed, {e(item['reason'])}</li>"
            for item in summary["allowed_skips"]
        )
        + "".join(
            f"<li><code>{e(node)}</code>: <strong class='failed'>not allowed</strong></li>"
            for node in summary["unexpected_skips"]
        )
        + "</ul>"
        if summary["allowed_skips"] or summary["unexpected_skips"]
        else "<p>None.</p>"
    )
    head = "<th>Passed</th><th>Failed</th><th>Skipped</th><th>Not run</th>"
    journeys = summary.get("acceptance")
    if journeys:
        steps = journeys["summary"] or {}
        rows = "".join(
            f"<tr><td>{e(str(j['title']))}</td><td class='{e(str(j['outcome']))}'>"
            f"{e(str(j['outcome']))}</td></tr>"
            for j in journeys["journeys"]
        )
        database = journeys["environment"].get("database") or {}
        acceptance = (
            f"<p>Run on this commit in a new database "
            f"(PostgreSQL {e(str(database.get('server_version', '')))}; CI runs it with the "
            "application image): "
            f"<strong class='{e(str(journeys['outcome']))}'>{e(str(journeys['outcome']))}"
            f"</strong>, {e(str(steps.get('steps_passed')))} of {e(str(steps.get('steps')))} "
            "steps passed. The steps, what each expected and observed, the lot records and "
            "certificates are in <a href='acceptance/report.html'>acceptance/report.html</a>."
            "</p><table><thead><tr><th>Journey</th><th>Outcome</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        acceptance = "<p>No acceptance journeys run is included in this pack.</p>"
    changes = (
        " <strong class='failed'>with uncommitted changes: these results are not those of the "
        "commit named</strong>"
        if summary["uncommitted_changes"]
        else ""
    )
    title = f"{PRODUCT} {summary['version']} validation pack"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>
body {{ font: 15px/1.45 system-ui, sans-serif; margin: 2rem auto; max-width: 70rem;
  padding: 0 1rem; color: #1b1f24; }}
table {{ border-collapse: collapse; width: 100%; margin: .5rem 0 1.5rem; }}
th, td {{ border: 1px solid #c8ccd1; padding: .3rem .5rem; text-align: left;
  vertical-align: top; }}
th {{ background: #eef0f2; }}
code {{ font-size: .85em; overflow-wrap: anywhere; }}
td:first-child a {{ white-space: nowrap; }}
@media (max-width: 40rem) {{ table {{ display: block; overflow-x: auto; }} }}
.passed {{ color: #146c2e; font-weight: 600; }}
.failed, .error {{ color: #a4161a; font-weight: 600; }}
.skipped, .not-run, .incomplete {{ color: #6b4e00; font-weight: 600; }}
.statement {{ border-left: 4px solid #6b4e00; padding: .5rem 1rem; background: #fbf6e9; }}
section {{ margin-bottom: 1.5rem; }}
@media print {{ details > table {{ display: table; }} }}
</style>
</head>
<body>
<h1>{e(title)}</h1>
<p class="statement">{e(summary["statement"])}</p>
<dl>
<dt>Status</dt><dd class="{e(summary["status"])}">{e(summary["status"])}</dd>
<dt>Commit</dt><dd><code>{e(summary["commit"])}</code>{changes}</dd>
<dt>Created</dt><dd>{e(summary["created_at"])}</dd>
<dt>Release notes</dt><dd><a href="release-notes.md">{e(summary["release_notes"])}</a></dd>
</dl>
<h2>Test suites</h2>
<table><thead><tr><th>Suite</th>{head}<th>Environment</th><th>Command and run</th></tr>
</thead>
<tbody>{suites}</tbody></table>
<h2>Acceptance journeys</h2>
{acceptance}
<h2>Requirements</h2>
<p>From <a href="documents/product.md">product.md</a>; the regulatory rows they cite are in
<a href="documents/regulations.md">regulations.md</a>. A requirement passes when at least one
test traced to it passed, none failed, every one ran and none was skipped without a reason
allowed by the map. A test that passes shows that the behaviour it
checks works as tested; it does not show that a requirement is met in full. The delivery
column states what is not implemented.</p>
<table><thead><tr><th>ID</th><th>Required outcome</th><th>Status</th>{head}</tr></thead>
<tbody>{requirement_rows}</tbody></table>
<h2>Project checks</h2>
<table><thead><tr><th>Check</th><th>Status</th>{head}</tr></thead>
<tbody>{project_rows}</tbody></table>
<h2>Results traced to no requirement</h2>
{untraced_list}
<h2>Skipped tests</h2>
<p>A skipped test leaves its requirement incomplete unless <code>traceability.toml</code> allows
the skip with a reason.</p>
{skipped_list}
<h2>Evidence by requirement</h2>
{details}
<h2>Files</h2>
<p><code>pack.json</code> summarizes this page; <code>requirements.csv</code> and
<code>traceability.csv</code> hold its tables; <code>results/</code> holds each suite's JUnit
file and environment as produced; <code>documents/</code> holds the requirements, the
regulatory matrix and the traceability map of this commit; <code>acceptance/</code>, when
present, holds the evidence folder of the acceptance journeys as written, with its own
<code>SHA256SUMS</code>. <code>SHA256SUMS</code> lists the
SHA-256 of every other file (check with <code>sha256sum -c SHA256SUMS</code>).</p>
</body>
</html>
"""


def _link(url):
    if not url:
        return "<br><small>not run in CI</small>"
    return f'<br><a href="{html.escape(url)}">{html.escape(url)}</a>'


def _codes(values):
    return ", ".join(f"<code>{html.escape(value)}</code>" for value in values)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check the traceability map")
    env = commands.add_parser("environment", help="record a suite's test environment")
    env.add_argument("--suite", required=True)
    env.add_argument("--root", default="", help="the suite's pytest root, from the repository")
    env.add_argument("--command", dest="run_command", default="")
    env.add_argument("--browser", action="store_true", help="record the Chromium version")
    env.add_argument("--output", required=True, type=Path)
    pack = commands.add_parser("build", help="assemble the validation pack")
    pack.add_argument("--results", action="append", required=True, type=Path)
    pack.add_argument(
        "--acceptance", type=Path, help="the evidence folder of manage.py acceptance_journeys"
    )
    pack.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            problems = check()
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1 if problems else 0
        if args.command == "environment":
            record = environment(args.suite, args.root, args.run_command, args.browser)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            return 0
        summary = build(args.results, args.output, acceptance=args.acceptance)
    except PackError as error:
        print(error, file=sys.stderr)
        return 2
    failing = [
        f"{r['id']} ({r['status']})" for r in summary["requirements"] if r["status"] != "passed"
    ]
    print(f"Validation pack {summary['status']}: {args.output}")
    if failing:
        print("Requirements not passed: " + ", ".join(failing), file=sys.stderr)
    if summary["acceptance"] and summary["acceptance"]["outcome"] != "passed":
        print("Acceptance journeys failed: see acceptance/report.html", file=sys.stderr)
    for label in ("failed_tests", "not_run", "unexpected_skips", "untraced_results"):
        if summary[label]:
            shown = summary[label][:50]
            more = len(summary[label]) - len(shown)
            print(f"{label.replace('_', ' ').capitalize()}: " + ", ".join(shown), file=sys.stderr)
            if more:
                print(f"... and {more} more (pack.json lists them all)", file=sys.stderr)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
