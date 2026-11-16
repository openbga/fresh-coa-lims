"""The browser journeys sign in and sign with the hashing work factor of a deployment."""

from django.contrib.auth.hashers import get_hasher


def test_browser_journeys_hash_at_the_deployed_work_factor():
    # The repository's root conftest.py lowers the PBKDF2 work factor for the PostgreSQL suite.
    # It is not loaded when the journeys run on their own, under e2e/pytest.ini.
    hasher = get_hasher()
    assert hasher.algorithm == "pbkdf2_sha256"
    assert hasher.iterations >= 1_000_000, "Run the journeys alone: pytest -c e2e/pytest.ini e2e"
