import pytest


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
