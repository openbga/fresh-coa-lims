import os
from pathlib import Path

import pytest


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
    from django.conf import settings

    config = settings.DATABASES["default"]
    config.setdefault("TEST", {})["NAME"] = f"test_{config['NAME']}_browser"
