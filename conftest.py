"""Shared pytest configuration for the PostgreSQL suite (`testpaths` in pyproject.toml).

The browser journeys run on their own under `e2e/pytest.ini`, so this file is not loaded for
them and they keep the hashing work factor of a deployment.
"""

import pytest

# Most tests create several accounts, each with a password and a signature PIN. At Django's
# PBKDF2 work factor of 1,000,000 iterations that hashing is most of the suite's run time.
# Only the work factor is lowered here. The hasher class, the `pbkdf2_sha256` algorithm name,
# salting and the stored format stay those of a deployment, so tests that look for stored
# hashes in logs, reports and documents still recognise them.
# tests/test_security_hardening.py checks the work factor a deployment uses.
TEST_PBKDF2_ITERATIONS = 1_000


@pytest.fixture(autouse=True, scope="session")
def reduced_hash_work_factor():
    from django.contrib.auth.hashers import PBKDF2PasswordHasher

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(PBKDF2PasswordHasher, "iterations", TEST_PBKDF2_ITERATIONS)
        yield
