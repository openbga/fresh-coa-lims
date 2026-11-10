"""Package-local settings: the shared settings plus reporting's own routes."""

from config.settings import *  # noqa: F403
from config.settings import INSTALLED_APPS

if "reporting" not in INSTALLED_APPS:
    INSTALLED_APPS = [*INSTALLED_APPS, "reporting"]
ROOT_URLCONF = "reporting.tests.urls"

# Tests only: a fast hasher keeps PIN/password fixtures cheap. Production keeps Django's default.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
