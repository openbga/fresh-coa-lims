import pytest

from catalog.tests.conftest import people  # noqa: F401
from catalog.tests.factories import approved_rules, approved_specification, material


@pytest.fixture
def configured(people):  # noqa: F811
    """An approved rule set and an approved specification whose two methods are in force."""
    rules = approved_rules(people["author"])
    spec = approved_specification(people["author"], people["approver"], material(people["author"]))
    return {"rules": rules, "specification": spec}
