import pytest

from laboratory.tests.conftest import people  # noqa: F401  (shared synthetic role users)


@pytest.fixture(autouse=True)
def fixture_requirement_provider(settings):
    """Synthetic requirements are an explicit test override, never a deployment default."""
    settings.ANALYTICAL_REQUIREMENT_PROVIDER = "analytical.fixtures.FixtureProvider"
