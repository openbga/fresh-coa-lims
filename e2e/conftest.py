import os
from pathlib import Path

import pytest

from scripts import validation_pack


def pytest_sessionstart(session):
    # The commit the tests run on goes into the JUnit file the validation pack is built from.
    validation_pack.record_checkout(session.config)


@pytest.fixture
def artifacts():
    """Directory for browser screenshots and failure pages: E2E_ARTIFACTS_DIR, or build/e2e."""
    path = Path(os.environ.get("E2E_ARTIFACTS_DIR") or "build/e2e")
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(autouse=True)
def source_static_assets(settings):
    # Django's static live-server handler resolves source paths, not hashed manifest names.
    # Production manifest delivery is independently checked by the container smoke job.
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture(scope="session")
def django_db_modify_db_settings():
    """The browser suite's own database: TEST_DATABASE_NAME when set, else test_<name>_browser.

    config/settings.py has already validated TEST_DATABASE_NAME (a separate test_ database), so
    sessions running at the same time with different names never share or drop each other's.
    """
    from django.conf import settings

    config = settings.DATABASES["default"]
    if not os.environ.get("TEST_DATABASE_NAME"):
        config.setdefault("TEST", {})["NAME"] = f"test_{config['NAME']}_browser"
    assert config["TEST"]["NAME"].startswith("test_")
    assert config["TEST"]["NAME"] != config["NAME"]
