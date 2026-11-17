"""Every list saves its column layout per user (grid.js + core/preferences.py): each list page's
{% list_results %} names a grid and its table is a {% grid_table %} with the same key, and every
declared column list (core.grids.Column) has stable, unique, slug keys and one locked column."""

import importlib
import re
from pathlib import Path

from django.conf import settings

from core.grids import Column

ROOT = Path(settings.BASE_DIR)
TAG = re.compile(r"{%\s*list_results\b[^%]*%}")

# Tables inside a record page are not lists of their own.
NOT_A_LIST = {
    "templates/quality/dashboard.html": "recent lots on an overview page",
    "analytical/templates/analytical/_raw_files.html": "files of one test record",
    "analytical/templates/analytical/batch_detail.html": "tests of one batch record",
    "analytical/templates/analytical/lot_testing.html": "tests of one lot record",
    "catalog/templates/catalog/specification_revision.html": "lines of one revision record",
    "laboratory/templates/ops/record.html": "rows of one record",
    "sampling/templates/sampling/lot_detail.html": "records of one lot",
    "suppliers/templates/suppliers/detail.html": "lots of one supplier record",
}
# Lists still to move onto {% grid_table %} (their owner removes each entry as it lands).
PENDING = {
    "laboratory/templates/ops/list.html",
}


def list_templates():
    for path in sorted(ROOT.glob("**/templates/**/*.html")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith((".venv/", "templates/includes/", "static")):
            continue
        text = path.read_text()
        if TAG.search(text):
            yield relative, text


def test_every_list_has_columns_saved_per_user():
    missing = []
    for relative, text in list_templates():
        if relative in NOT_A_LIST or relative in PENDING:
            continue
        keys = {m.group(1) for m in re.finditer(r'list_results\b[^%]*\bgrid="([^"]+)"', text)}
        tables = {m.group(1) for m in re.finditer(r'grid_table\b[^%]*\bgrid="([^"]+)"', text)}
        if not keys or keys != tables:
            missing.append(relative)
    assert not missing, f"lists without a grid_table and list_results grid key: {missing}"


def test_pending_lists_are_still_pending():
    done = []
    for relative, text in list_templates():
        if relative in PENDING and "{% grid_table" in text:
            done.append(relative)
    assert not done, f"remove from PENDING: {done}"


def test_declared_columns_have_stable_keys():
    for module_name in ("quality.views", "accounts.views", "core.views"):
        module = importlib.import_module(module_name)
        for name, value in vars(module).items():
            if isinstance(value, tuple) and value and all(isinstance(c, Column) for c in value):
                keys = [column.key for column in value]
                assert len(keys) == len(set(keys)), name
                assert all(re.fullmatch(r"[a-z][a-z0-9-]*", key) for key in keys), name
                assert any(column.locked for column in value), name
