import pytest

from .factories import person


@pytest.fixture
def people(db):
    return {
        "author": person("qa-author", "quality"),
        "approver": person("qa-approver", "quality"),
        "analyst": person("analyst-a", "analyst"),
        "reviewer": person("reviewer-a", "reviewer"),
        "admin": person("admin-a", "admin"),
        "auditor": person("auditor-a", "auditor"),
        "dual": person("dual-role", "quality", "analyst", "reviewer"),
    }
