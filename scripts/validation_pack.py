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
    python scripts/validation_pack.py build --results DIR [--results DIR ...] --output DIR
        Assemble the pack from result directories, each holding junit.xml and
        environment.json. Exits 1 unless no test failed, every traced test ran and every
        requirement has a passing test.

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
PRODUCT = "OpenBGA Fresh CoA LIMS"
MAP = "docs/traceability.toml"
REQUIREMENTS = "docs/product.md"
BROWSER_SUITE = "e2e"
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
            for node in tree.body:
                if _is_test(node):
                    tests[f"{path}::{node.name}"] = _summary(node)
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    for item in node.body:
                        if _is_test(item):
                            tests[f"{path}::{node.name}::{item.name}"] = _summary(item)
    return tests


def _is_test(node):
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def _summary(node):
    doc = ast.get_docstring(node) or ""
    return " ".join(doc.split("\n\n")[0].split())


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
    entries = _entries(traced, project)
    for entry in sorted(set(entries)):
        path = entry.split("::")[0]
        if not (root / path).exists():
            problems.append(f"{MAP} names {entry}, which does not exist.")
        elif "::" in entry and not any(covers(entry, node_id) for node_id in tests):
            problems.append(f"{MAP} names {entry}, which is not a test.")
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

    with psycopg.connect(url, connect_timeout=10) as connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
    return f"PostgreSQL {version}"


def _commit():
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _uncommitted(root):
    """Whether the checkout differs from its commit (or cannot be read as one)."""
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False
    )
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
    return env, cases


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


def build(results, output, root=None):
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

    requirements = read_requirements(root)
    traced, project = read_map(root)
    descriptions = discover_tests(root)
    rows = [
        {**case, "suite": suite["environment"]["suite"]}
        for suite in suites
        for case in suite["cases"]
    ]
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
                "status": _status(matched),
            }
        )
    entries = [entry for _, _, values in groups for entry in values]
    untraced = [r for r in rows if not any(covers(entry, _base(r["node"])) for entry in entries)]
    failed = [r for r in rows if r["outcome"] in ("failed", "error")]
    uncommitted = _uncommitted(root) or any(
        suite["environment"].get("uncommitted_changes", True) for suite in suites
    )
    if failed:
        status = "failed"
    elif (
        uncommitted
        or any(item["not_run"] for item in evidence)
        or any(item["status"] != "passed" for item in evidence if item["requirement"])
    ):
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
        "not_run": sorted({node for item in evidence for node in item["not_run"]}),
    }

    output.mkdir(parents=True)
    for suite in suites:
        target = output / "results" / suite["environment"]["suite"]
        target.mkdir(parents=True)
        for name in ("junit.xml", "environment.json"):
            shutil.copyfile(suite["directory"] / name, target / name)
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
        ["requirement", "test", "suite", "outcome", "seconds", "description", "message"],
        [
            [item["id"], r["node"], r["suite"], r["outcome"], f"{r['seconds']:.3f}"]
            + [descriptions.get(_base(r["node"]), ""), r["message"]]
            for item in evidence
            for r in sorted(item["tests"], key=lambda r: r["node"])
        ]
        + [
            [item["id"], node, "", "not run", "", descriptions[node], ""]
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


def _status(cases):
    if any(case["outcome"] in ("failed", "error") for case in cases):
        return "failed"
    if any(case["outcome"] == "passed" for case in cases):
        return "passed"
    return "not run"


def _write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


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
            f"<td class='{e(r['outcome'])}'>{e(r['outcome'])}</td>"
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
        f"<td><code>{e(s['environment']['command'])}</code></td></tr>"
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
    run = summary["suites"][0]["environment"].get("run") if summary["suites"] else ""
    head = "<th>Passed</th><th>Failed</th><th>Skipped</th><th>Not run</th>"
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
.passed {{ color: #146c2e; font-weight: 600; }}
.failed, .error {{ color: #a4161a; font-weight: 600; }}
.skipped, .not-run {{ color: #6b4e00; font-weight: 600; }}
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
<dt>Test run</dt><dd>{f'<a href="{e(run)}">{e(run)}</a>' if run else "Not run in CI"}</dd>
<dt>Release notes</dt><dd><a href="release-notes.md">{e(summary["release_notes"])}</a></dd>
</dl>
<h2>Test suites</h2>
<table><thead><tr><th>Suite</th>{head}<th>Environment</th><th>Command</th></tr></thead>
<tbody>{suites}</tbody></table>
<h2>Requirements</h2>
<p>From <a href="documents/product.md">product.md</a>; the regulatory rows they cite are in
<a href="documents/regulations.md">regulations.md</a>. A requirement passes when at least one
test traced to it passed and none failed. A test that passes shows that the behaviour it
checks works as tested; it does not show that a requirement is met in full. The delivery
column states what is not implemented.</p>
<table><thead><tr><th>ID</th><th>Required outcome</th><th>Status</th>{head}</tr></thead>
<tbody>{requirement_rows}</tbody></table>
<h2>Project checks</h2>
<table><thead><tr><th>Check</th><th>Status</th>{head}</tr></thead>
<tbody>{project_rows}</tbody></table>
<h2>Results traced to no requirement</h2>
{untraced_list}
<h2>Evidence by requirement</h2>
{details}
<h2>Files</h2>
<p><code>pack.json</code> summarizes this page; <code>requirements.csv</code> and
<code>traceability.csv</code> hold its tables; <code>results/</code> holds each suite's JUnit
file and environment as produced; <code>documents/</code> holds the requirements, the
regulatory matrix and the traceability map of this commit. <code>SHA256SUMS</code> lists the
SHA-256 of every other file (check with <code>sha256sum -c SHA256SUMS</code>).</p>
</body>
</html>
"""


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
        summary = build(args.results, args.output)
    except PackError as error:
        print(error, file=sys.stderr)
        return 2
    failing = [r["id"] for r in summary["requirements"] if r["status"] != "passed"]
    print(f"Validation pack {summary['status']}: {args.output}")
    if failing:
        print("Requirements without passing evidence: " + ", ".join(failing), file=sys.stderr)
    for label in ("failed_tests", "not_run"):
        if summary[label]:
            shown = summary[label][:50]
            more = len(summary[label]) - len(shown)
            print(f"{label.replace('_', ' ').capitalize()}: " + ", ".join(shown), file=sys.stderr)
            if more:
                print(f"... and {more} more (pack.json lists them all)", file=sys.stderr)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
