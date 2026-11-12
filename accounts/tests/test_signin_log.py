import logging

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD = "Synthetic-signin-2026!"


@pytest.fixture
def signin_records(caplog):
    logger = logging.getLogger("openbga.signin")
    logger.addHandler(caplog.handler)  # The logger does not propagate to the root handler.
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)


def messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "openbga.signin"]


def test_sign_in_and_out_are_logged_with_request_id(client, django_user_model, signin_records):
    django_user_model.objects.create_user("signin_analyst", password=PASSWORD)
    rid = "8ebfa3c3-8929-4885"
    response = client.post(
        reverse("login"),
        {"username": "signin_analyst", "password": PASSWORD},
        HTTP_RNDR_ID=rid,
    )
    assert response.status_code == 302
    client.post(reverse("logout"), HTTP_RNDR_ID="b-2")
    assert messages(signin_records) == [
        f"signin.success user=signin_analyst request_id={rid}",
        "signout user=signin_analyst request_id=b-2",
    ]


def test_failed_attempts_never_log_passwords_or_unknown_usernames(
    client, django_user_model, signin_records
):
    django_user_model.objects.create_user("signin_reviewer", password=PASSWORD)
    client.post(reverse("login"), {"username": "signin_reviewer", "password": "wrong-Secret-1"})
    client.post(reverse("login"), {"username": "Typed-Secret-99", "password": "wrong-Secret-2"})
    lines = messages(signin_records)
    assert lines == [
        "signin.failed user=signin_reviewer request_id=-",
        "signin.failed user=<unknown> request_id=-",
    ]
    assert not any("Secret" in line for line in lines)


def test_locked_account_attempt_is_logged_as_failed(
    client, django_user_model, settings, signin_records
):
    settings.LOGIN_FAILURE_LIMIT = 1
    django_user_model.objects.create_user("signin_quality", password=PASSWORD)
    client.post(reverse("login"), {"username": "signin_quality", "password": "wrong-pass-1"})
    response = client.post(reverse("login"), {"username": "signin_quality", "password": PASSWORD})
    assert response.status_code == 200  # Refused while locked, even with the right password.
    assert messages(signin_records) == ["signin.failed user=signin_quality request_id=-"] * 2


def test_malformed_request_id_is_not_logged(client, django_user_model, signin_records):
    django_user_model.objects.create_user("signin_auditor", password=PASSWORD)
    client.post(
        reverse("login"),
        {"username": "signin_auditor", "password": PASSWORD},
        HTTP_RNDR_ID="x y=forged",
    )
    assert messages(signin_records) == ["signin.success user=signin_auditor request_id=-"]
