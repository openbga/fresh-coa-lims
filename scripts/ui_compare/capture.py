"""Before/after screenshots of the UI for a pull request.

"Before" is origin/develop, served from a temporary worktree on 127.0.0.1:8013; "after" is the
running development server (default http://127.0.0.1:8010). Both read the same database unless
--before-database-url points "before" at a copy, so every page shows the same synthetic records.
See README.md in this directory.

    uv run --group e2e python scripts/ui_compare/capture.py [--pages ID_OR_PATH,...] [--after-only]
    uv run --group e2e python scripts/ui_compare/capture.py --list
"""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / ".local" / "ui-compare"
SHOTS = OUT / "shots"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
THEMES = ("light", "dark")
ANONYMOUS = ""
ACCOUNTS = (
    "demo_admin",
    "demo_analyst",
    "demo_reviewer",
    "demo_quality",
    "demo_config_author",
    "demo_auditor",
)  # synthetic demo accounts only
CONFIG = {
    "after": "http://127.0.0.1:8010",
    "before": "http://127.0.0.1:8013",
    "tree": OUT / "develop",
}


# ------------------------------------------------------------------------------- page actions


def settle(page: Page) -> None:
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(400)


def open_help(page: Page) -> None:
    toggle = page.locator(
        "[data-pagedocs-toggle]:visible, [aria-controls*=pagedocs]:visible,"
        " button:has-text('Help'):visible"
    ).first
    toggle.click()
    page.wait_for_timeout(600)
    page.mouse.move(600, 600)
    page.evaluate("document.querySelectorAll('.tooltip').forEach(t => t.remove())")


def open_more(page: Page) -> None:
    page.locator("main .dropdown-toggle:visible").first.click()
    page.wait_for_timeout(300)


# ------------------------------------------------------------------------------- page registry

# id: (title, account, path or "@target" resolved by targets.py, action)
TIER1 = {
    "dashboard": ("Dashboard", "demo_quality", "/", None),
    "dashboard-analyst": ("Dashboard (analyst)", "demo_analyst", "/", None),
    "lots": ("Lots list", "demo_quality", "/lots/", None),
    "lot-quarantine": ("Lot record, quarantine (analyst)", "demo_analyst", "@lot-quarantine", None),
    "lot-ready": ("Lot record, ready for disposition", "demo_quality", "@lot-ready", None),
    "lot-applicability": (
        "Lot record, applicability hold",
        "demo_quality",
        "@lot-applicability",
        None,
    ),
    "lot-oos": ("Lot record, open OOS investigation", "demo_quality", "@lot-oos", None),
    "lot-stability-hold": (
        "Lot record, stability hold",
        "demo_quality",
        "@lot-stability-hold",
        None,
    ),
    "lot-released": ("Lot record, released, CoA issued", "demo_quality", "@lot-released", None),
    "lot-amended": ("Lot record, CoA amended", "demo_quality", "@lot-amended", None),
    "lot-rejected": ("Lot record, rejected", "demo_quality", "@lot-rejected", None),
    "lot-cancelled": ("Lot record, cancelled", "demo_quality", "@lot-cancelled", None),
    "lot-testing": ("Lot testing", "demo_analyst", "@lot-testing", None),
    "test-open": ("Test record, open", "demo_analyst", "@test-open", None),
    "test-submitted": ("Test record, awaiting review", "demo_reviewer", "@test-submitted", None),
    "test-oos": ("Test record, out of specification", "demo_quality", "@test-oos", None),
    "test-invalidated": ("Test record, invalidated", "demo_quality", "@test-invalidated", None),
    "test-superseded": ("Test record, superseded", "demo_quality", "@test-superseded", None),
    "test-retest": ("Test record, retest", "demo_analyst", "@test-retest", None),
    "investigation": ("Investigation record", "demo_quality", "@investigation", None),
    "batch": ("QC batch record", "demo_reviewer", "@batch", None),
    "sampling-lot": ("Sampling lot record", "demo_analyst", "@sampling-lot", None),
    "certificates": ("Certificates list", "demo_quality", "/reports/", None),
    "certificate": ("Certificate record", "demo_quality", "@certificate", None),
    "certificate-version": (
        "Certificate version",
        "demo_auditor",
        "@certificate-version",
        None,
    ),
    "study": ("Stability study record", "demo_analyst", "@study", None),
    "pull-overdue": ("Stability pull, overdue", "demo_analyst", "@pull-overdue", None),
    "sign-in": ("Sign-in page", ANONYMOUS, "/accounts/login/", None),
    "sign-review": ("Sign review of a test", "demo_reviewer", "@sign-review", None),
    "sign-disposition": ("Sign QC disposition", "demo_quality", "@sign-disposition", None),
    "sign-coa-issue": ("Issue CoA preview", "demo_quality", "@sign-coa-issue", None),
    "sign-coa-amend": ("Amend CoA preview", "demo_quality", "@sign-coa-amend", None),
    "sign-rule": ("Approve a rule set", "demo_quality", "@sign-rule", None),
    "sign-spec": ("Approve a specification version", "demo_quality", "@sign-spec", None),
    "sign-method": ("Approve a method version", "demo_quality", "@sign-method", None),
    "help": ("Page help on the lot record", "demo_quality", "@lot-ready", open_help),
}
PAGES = {}
for _pid, _page in TIER1.items():
    PAGES[_pid] = (*_page, DESKTOP)
    PAGES[f"{_pid}-390"] = (f"{_page[0]} at 390", *_page[1:], PHONE)

OVERFLOW_JS = """() => {
  const out = [];
  if (document.documentElement.scrollWidth > innerWidth + 1)
    out.push(`page ${document.documentElement.scrollWidth}px > ${innerWidth}px`);
  return out;
}"""


def selected_pages(spec: str) -> dict:
    """Registry ids, or ad-hoc paths: "/path/" (demo_admin) or "demo_quality:/path/"."""
    if not spec:
        return dict(PAGES)
    pages = {}
    for item in filter(None, (s.strip() for s in spec.split(","))):
        account, _, path = item.rpartition(":") if ":/" in item else ("", "", item)
        if path.startswith("/"):
            account = account or "demo_admin"
            if account not in ACCOUNTS:
                sys.exit(f"Unknown account {account!r}: use one of {', '.join(ACCOUNTS)}.")
            pid = re.sub(r"[^a-z0-9]+", "-", f"{account}{path}".lower()).strip("-")
            pages[pid] = (f"{path} ({account})", account, path, None, DESKTOP)
        elif item in PAGES:
            pages[item] = PAGES[item]
        else:
            sys.exit(f"Unknown page {item!r}. Run with --list to see the ids.")
    return pages


# ------------------------------------------------------------------------------- environment


def run(cmd: list[str], cwd: Path = REPO, env=None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True, env=env).stdout


def wait_http(url: str, seconds: int = 180) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=3)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"{url} did not answer within {seconds}s")


def goto(page: Page, url: str) -> None:
    """Navigate, riding out a development-server autoreload (connection refused for a moment)."""
    for attempt in range(3):
        try:
            page.goto(url)
            return
        except Exception as exc:
            if "ERR_CONNECTION_REFUSED" not in str(exc) or attempt == 2:
                raise
            wait_http(url.split("/", 3)[0] + "//" + url.split("/", 3)[2] + "/accounts/login/")


ADDITIVE = {"CreateModel", "AddIndex", "AddConstraint"}


def migration_problems() -> list[str]:
    """Migrations develop's code cannot share a database with.

    Allowed: new migration files whose operations are all CreateModel, AddIndex or AddConstraint,
    or AddField with null=True, a default or a db_default. Edited or deleted develop migrations
    are not.
    """
    problems, new_files = [], []
    edited = run(["git", "diff", "origin/develop", "--name-status", "--", "*/migrations/*"])
    for line in filter(None, edited.splitlines()):
        status, path = line.split("\t", 1)
        if status.startswith("A"):
            new_files.append(path)
        else:
            problems.append(f"{path}: {status} changes a develop migration")
    new_files += run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "*/migrations/*"]
    ).split()
    for path in new_files:
        if not path.endswith(".py") or path.endswith("__init__.py"):
            continue
        for op in re.split(r"(?=migrations\.[A-Z]\w+\()", (REPO / path).read_text())[1:]:
            name = re.match(r"migrations\.(\w+)", op).group(1)
            additive_field = name == "AddField" and re.search(r"null=True|default=|db_default=", op)
            if name not in ADDITIVE and not additive_field:
                problems.append(f"{path}: {name} is not additive")
    return problems


def preflight(before_database_url: str) -> None:
    if not os.environ.get("DEMO_PASSWORD"):
        sys.exit("DEMO_PASSWORD is not set. Load the environment first: set -a; . ./.env; set +a")
    if not before_database_url:
        problems = migration_problems()
        if problems:
            sys.exit(
                "Before and after cannot share the database (use --before-database-url with a "
                "copy):\n  " + "\n  ".join(problems)
            )
    try:
        urllib.request.urlopen(CONFIG["after"] + "/accounts/login/", timeout=5)
    except Exception:
        sys.exit(f"No development server answers on {CONFIG['after']}.")


def before_env(database_url: str) -> dict:
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    }
    if database_url:
        env["DATABASE_URL"] = database_url
    return env


def remove_worktree() -> None:
    tree = CONFIG["tree"]
    if tree.exists() or str(tree) in run(["git", "worktree", "list"]):
        subprocess.run(["git", "worktree", "remove", "--force", str(tree)], cwd=REPO)
        subprocess.run(["git", "worktree", "prune"], cwd=REPO)
    shutil.rmtree(tree, ignore_errors=True)


def start_before(database_url: str, reuse: bool) -> subprocess.Popen:
    tree, env = CONFIG["tree"], before_env(database_url)
    if not (reuse and (tree / "manage.py").exists()):
        remove_worktree()
        tree.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "worktree", "add", "--detach", str(tree), "origin/develop"])
    for cmd in (
        ["uv", "sync", "--frozen"],
        ["uv", "run", "python", "manage.py", "collectstatic", "--noinput"],
    ):
        subprocess.run(cmd, cwd=tree, env=env, check=True, capture_output=True)
    log = open(OUT / "before-server.log", "w")  # noqa: SIM115 (lives as long as the server)
    proc = subprocess.Popen(
        ["uv", "run", "python", "manage.py", "runserver", CONFIG["before"][7:], "--noreload"],
        cwd=tree,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    wait_http(CONFIG["before"] + "/accounts/login/")
    return proc


def stop_before(proc: subprocess.Popen | None, keep: bool) -> None:
    if proc and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    if not keep:
        remove_worktree()


def resolve_targets(wanted: set[str]) -> dict[str, str]:
    """Record paths, found once in the after database (same records on both sides)."""
    if not wanted:
        return {}
    out = run(
        ["uv", "run", "python", "manage.py", "shell", "-c", (HERE / "targets.py").read_text()],
        env={**os.environ, "UI_COMPARE_TARGETS": ",".join(sorted(wanted))},
    )
    line = next(line for line in out.splitlines() if line.startswith("{"))
    return json.loads(line)


# ------------------------------------------------------------------------------- capture


def login(browser, base: str, account: str, theme: str):
    ctx = browser.new_context(viewport=DESKTOP, color_scheme=theme, reduced_motion="reduce")
    ctx.add_init_script(f"try {{ localStorage.setItem('vr-theme', '{theme}'); }} catch (e) {{}}")
    page = ctx.new_page()
    if account == ANONYMOUS:
        return ctx, page
    goto(page, base + "/accounts/login/")
    page.fill("input[name=username]", account)
    page.fill("input[name=password]", os.environ["DEMO_PASSWORD"])
    page.locator("form button[type=submit]").first.click()
    page.wait_for_load_state("networkidle")
    if "/accounts/login" in page.url:
        raise RuntimeError(f"Sign-in failed for {account} on {base}")
    return ctx, page


def capture(browser, side: str, base: str, pages: dict, urls: dict, result: dict) -> None:
    for theme in THEMES:
        sessions = {}
        try:
            for pid, (_title, account, target, action, viewport) in pages.items():
                stem = SHOTS / f"{pid}-{side}-{theme}"
                try:
                    path = urls.get(target[1:]) if target.startswith("@") else target
                    if not path:
                        raise RuntimeError(f"no record for {target} in the database")
                    if account not in sessions:
                        sessions[account] = login(browser, base, account, theme)
                    page = sessions[account][1]
                    page.set_viewport_size(viewport)
                    goto(page, base + path)
                    settle(page)
                    if action:
                        action(page)
                    result["overflow"][f"{pid}-{side}-{theme}"] = page.evaluate(OVERFLOW_JS)
                    shot = {"animations": "disabled", "caret": "hide"}
                    page.screenshot(path=f"{stem}.png", **shot)
                    page.screenshot(path=f"{stem}-full.png", full_page=True, **shot)
                    if action is open_help:  # the help panel stays open on later pages: reset
                        sessions.pop(account)[0].close()
                    print(f"  {side:6} {theme:5} {pid}", flush=True)
                except Exception as exc:  # keep going; the page lists the gap
                    result["errors"].append(
                        f"{side} {theme} {pid}: {type(exc).__name__}: {exc}"[:300]
                    )
                    print("  !", result["errors"][-1], flush=True)
                    for stale in (Path(f"{stem}.png"), Path(f"{stem}-full.png")):
                        stale.unlink(missing_ok=True)  # never show an old shot as current
        finally:
            for ctx, _ in sessions.values():
                ctx.close()


def diff_stats(pids) -> dict:
    """Share of changed pixels per page and theme, plus a highlighted diff image."""
    from PIL import Image, ImageChops

    stats = {}
    for pid in pids:
        for theme in THEMES:
            a, b = SHOTS / f"{pid}-before-{theme}.png", SHOTS / f"{pid}-after-{theme}.png"
            if not (a.exists() and b.exists()):
                continue
            before, after = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
            if before.size != after.size:
                after = after.resize(before.size)
            mask = (
                ImageChops.difference(before, after)
                .convert("L")
                .point(lambda v: 255 if v > 10 else 0)
            )
            overlay = Image.blend(after, Image.new("RGB", after.size, (255, 255, 255)), 0.7)
            overlay.paste(Image.new("RGB", after.size, (230, 40, 90)), mask=mask)
            overlay.save(SHOTS / f"{pid}-diff-{theme}.png")
            stats[f"{pid}-{theme}"] = round(
                100 * mask.histogram()[255] / (mask.width * mask.height), 1
            )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--pages", default="", help="ids from --list, '/path/' or 'demo_quality:/path/'"
    )
    parser.add_argument("--after-only", action="store_true", help="reuse the existing before shots")
    parser.add_argument("--list", action="store_true", help="print the page ids and exit")
    parser.add_argument("--after", default=CONFIG["after"], help="after server base URL")
    parser.add_argument("--before-port", type=int, default=8013, help="port for origin/develop")
    parser.add_argument(
        "--before-database-url",
        default="",
        help="database for the before server (a copy); default: the same DATABASE_URL",
    )
    parser.add_argument(
        "--before-tree", default=str(CONFIG["tree"]), help="where the develop worktree goes"
    )
    parser.add_argument(
        "--keep-before", action="store_true", help="keep (and reuse) the develop worktree"
    )
    args = parser.parse_args()
    if args.list:
        for pid, page in PAGES.items():
            print(f"{pid:26} {page[0]}  [{page[1] or 'signed out'} {page[2]}]")
        return 0
    CONFIG.update(
        after=args.after.rstrip("/"),
        before=f"http://127.0.0.1:{args.before_port}",
        tree=Path(args.before_tree).resolve(),
    )

    pages = selected_pages(args.pages)
    preflight(args.before_database_url)
    SHOTS.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    result = {"errors": [], "overflow": {}}
    proc = None
    try:
        urls = resolve_targets({t[1:] for _, _, t, _, _ in pages.values() if t.startswith("@")})
        if not args.after_only:
            print(f"Starting origin/develop on {CONFIG['before']} …", flush=True)
            proc = start_before(args.before_database_url, args.keep_before)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(ignore_default_args=["--hide-scrollbars"])
            for side, base in [("after", CONFIG["after"])] + (
                [] if args.after_only else [("before", CONFIG["before"])]
            ):
                capture(browser, side, base, pages, urls, result)
            browser.close()
    finally:
        stop_before(proc, args.keep_before)

    known = {p["id"]: p for p in old.get("pages", [])}
    for pid, (title, account, target, _action, viewport) in pages.items():
        path = urls.get(target[1:], "") if target.startswith("@") else target
        known[pid] = {
            "id": pid,
            "title": title,
            "user": account or "signed out",
            "path": path,
            "viewport": f"{viewport['width']}×{viewport['height']}",
        }
    order = {pid: i for i, pid in enumerate(PAGES)}
    manifest = {
        "captured": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "before_ref": run(["git", "rev-parse", "--short", "origin/develop"]).strip(),
        "after_ref": run(["git", "rev-parse", "--short", "HEAD"]).strip() + " + working tree",
        "after_url": CONFIG["after"],
        "before_url": CONFIG["before"],
        "pages": sorted(known.values(), key=lambda p: order.get(p["id"], len(order))),
        "errors": result["errors"],
        "overflow": {**old.get("overflow", {}), **result["overflow"]},
        "diff": {**old.get("diff", {}), **diff_stats(pages)},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    subprocess.run([sys.executable, str(HERE / "build.py"), str(OUT)], check=True)
    if result["errors"]:
        print("Capture gaps:\n  " + "\n  ".join(result["errors"]))
    print(OUT / "index.html")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
