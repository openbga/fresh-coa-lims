"""Single sign-on with the organization's identity provider (OpenID Connect code flow + PKCE).

Each test runs the local provider in accounts/tests/oidc_provider.py: the application fetches
its discovery document, exchanges the code at its token endpoint and checks the ID token against
its key set over HTTP, as it would with a real provider.
"""

import os
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from accounts import single_sign_on
from accounts.models import LoginThrottle, SingleSignOnLink
from accounts.tests.oidc_provider import CLIENT_ID, CLIENT_SECRET, Provider
from accounts.tests.test_two_factor import code, enable
from accounts.views import PENDING_SIGN_IN, SSO_PENDING
from core.models import AuditEvent, ElectronicSignature
from core.services import set_pin

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "Synthetic-two-factor-pass-318!"  # As accounts.tests.test_two_factor.make_user sets.
PIN = "73519246"
LOGIN = "/accounts/login/"
START = "/accounts/login/sso/"
CALLBACK = "/accounts/login/sso/callback/"
PAGE = "/accounts/single-sign-on/"
VERIFY = "/accounts/login/verify/"


def make_user(username, roles=(), **extra):
    user = get_user_model().objects.create_user(
        username=username, password=PASSWORD, first_name="Synthetic", last_name=username, **extra
    )
    user.groups.set([Group.objects.get_or_create(name=role)[0] for role in roles])
    return user


def fresh(user):
    return get_user_model().objects.get(pk=user.pk)


@pytest.fixture
def provider(settings):
    with Provider() as running:
        settings.OIDC_ISSUER = running.issuer
        settings.OIDC_CLIENT_ID = CLIENT_ID
        settings.OIDC_CLIENT_SECRET = CLIENT_SECRET
        settings.OIDC_PROVIDER_NAME = "Synthetic Org"
        settings.SINGLE_SIGN_ON = True
        single_sign_on._client.cache_clear()
        single_sign_on._unavailable_until.clear()
        yield running
    single_sign_on._client.cache_clear()
    single_sign_on._unavailable_until.clear()


@pytest.fixture
def analyst():
    return make_user("analyst.sso", ["analyst"])


@pytest.fixture
def manager():
    user = make_user("manager.sso", ["admin"])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def link(user, subject="sub-analyst", label="analyst@synthetic.example"):
    return SingleSignOnLink.objects.create(
        user=user,
        issuer=single_sign_on.settings.OIDC_ISSUER,
        subject=subject,
        label=label,
        created_at=single_sign_on.timezone.now(),
    )


def to_provider(response):
    """Follow the application's redirect (sign-in) or link (linking) to the provider; returns
    the callback path."""
    if response.status_code == 200 and response.context and response.context.get("continue_url"):
        target = response.context["continue_url"]
        assert f'href="{target.replace("&", "&amp;")}"'.encode() in response.content
    else:
        assert response.status_code == 302, getattr(response, "content", b"")[:500]
        target = response["Location"]
    answer = requests.get(target, allow_redirects=False, timeout=10)
    assert answer.status_code == 302
    location = urlsplit(answer.headers["Location"])
    assert location.path == CALLBACK
    return f"{location.path}?{location.query}"


def sign_in(client, provider, subject, start=START):
    provider.next_subject = subject
    return client.get(to_provider(client.get(start)))


def messages_of(response):
    return [str(m) for m in response.wsgi_request._messages] if response.wsgi_request else []


def signed_in_as(client):
    return client.session.get("_auth_user_id")


# --- Off unless configured ----------------------------------------------------------------


def test_off_without_configuration(client, analyst):
    page = client.get(LOGIN)
    assert b"Sign in with" not in page.content.replace(b"Sign in with a passkey", b"")
    assert client.get(START).status_code == 404
    assert client.get(CALLBACK).status_code == 404
    client.force_login(analyst)
    assert client.get(PAGE).status_code == 404
    assert b"Organization sign-in" not in client.get(reverse("accounts:access")).content


def test_settings_refuse_partial_or_insecure_configuration():
    def start(**env):
        environment = {**os.environ, "SECRET_KEY": "x" * 50, "DEBUG": "false", **env}
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            env=environment,
            capture_output=True,
            text=True,
        )

    partial = start(OIDC_ISSUER="https://id.synthetic.example")
    assert partial.returncode and "needs OIDC_ISSUER, OIDC_CLIENT_ID" in partial.stderr
    full = {"OIDC_CLIENT_ID": "lims", "OIDC_CLIENT_SECRET": "synthetic"}
    insecure = start(OIDC_ISSUER="http://id.synthetic.example", **full)
    assert insecure.returncode and "https URL" in insecure.stderr
    no_openid = start(OIDC_ISSUER="https://id.synthetic.example", OIDC_SCOPES="email", **full)
    assert no_openid.returncode and "openid" in no_openid.stderr
    assert start(OIDC_ISSUER="https://id.synthetic.example", **full).returncode == 0


# --- Sign-in --------------------------------------------------------------------------------


def test_sign_in_page_offers_the_provider(client, provider):
    page = client.get(LOGIN + "?next=/catalog/")
    assert b"Sign in with Synthetic Org" in page.content
    assert b'href="/accounts/login/sso/?next=/catalog/"' in page.content


def test_request_uses_code_flow_with_pkce_state_nonce_and_prompt(client, provider, analyst):
    link(analyst)
    response = client.get(START)
    request = provider.authorize_requests or None
    assert request is None  # Nothing reached the provider yet: the browser goes there.
    target = urlsplit(response["Location"])
    params = {k: v[0] for k, v in parse_qs(target.query).items()}
    assert f"{target.scheme}://{target.netloc}{target.path}" == f"{provider.issuer}/authorize"
    assert params["response_type"] == "code"
    assert params["client_id"] == CLIENT_ID
    assert params["redirect_uri"] == "http://testserver" + CALLBACK
    assert params["code_challenge_method"] == "S256" and len(params["code_challenge"]) == 43
    assert len(params["state"]) >= 43 and len(params["nonce"]) >= 43
    assert params["prompt"] == "login"
    assert params["scope"].split() == ["openid", "email", "profile"]
    pending = client.session[SSO_PENDING]
    assert pending["purpose"] == "sign_in" and pending["state"] == params["state"]


def test_linked_account_signs_in(client, provider, analyst):
    found = link(analyst)
    response = sign_in(client, provider, "sub-analyst", start=START + "?next=/catalog/")
    assert response.status_code == 302 and response["Location"] == "/catalog/"
    assert signed_in_as(client) == str(analyst.pk)
    assert client.session["sign_in_factors"] == ["identity_provider"]
    assert client.session["account_epoch"] == fresh(analyst).session_epoch
    assert SSO_PENDING not in client.session
    found.refresh_from_db()
    assert found.last_used_at is not None
    token_request = provider.token_requests[-1]
    assert token_request["grant_type"] == "authorization_code" and token_request["code_verifier"]


def test_next_outside_the_site_is_ignored(client, provider, analyst):
    link(analyst)
    response = sign_in(client, provider, "sub-analyst", start=START + "?next=https://x.example/")
    assert response["Location"] == "/"


def test_identity_without_link_is_refused_and_not_counted(client, provider, analyst):
    link(analyst)
    response = sign_in(client, provider, "sub-someone-else")
    assert response.status_code == 302 and response["Location"] == LOGIN
    assert not signed_in_as(client)
    assert single_sign_on.NOT_LINKED in messages_of(response)
    assert not LoginThrottle.objects.filter(user=analyst, failures__gt=0).exists()


def test_inactive_or_paused_account_is_refused(client, provider, analyst):
    link(analyst)
    for _ in range(single_sign_on.settings.LOGIN_FAILURE_LIMIT):
        Client().post(LOGIN, {"username": analyst.username, "password": "wrong-synthetic"})
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.PAUSED in messages_of(response)
    LoginThrottle.objects.filter(user=analyst).update(locked_until=None, failures=0)
    get_user_model().objects.filter(pk=analyst.pk).update(is_active=False)
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.CANNOT_SIGN_IN in messages_of(response)


def test_account_with_second_factor_is_asked_for_it(client, provider, analyst):
    device, _codes = enable(analyst)
    link(analyst)
    response = sign_in(client, provider, "sub-analyst")
    assert response.status_code == 302 and response["Location"] == VERIFY
    assert not signed_in_as(client)
    assert client.session[PENDING_SIGN_IN]["first"] == "identity_provider"
    page = client.get(VERIFY)
    assert b"Your organization signed you in." in page.content
    assert b"Your password was accepted" not in page.content
    response = client.post(VERIFY, {"otp_code": "000000" if code(device) != "000000" else "1"})
    assert response.status_code == 422 and not signed_in_as(client)
    response = client.post(VERIFY, {"otp_code": code(device, 1)})  # Setup spent this step.
    assert response.status_code == 302 and signed_in_as(client) == str(analyst.pk)
    assert client.session["sign_in_factors"] == ["identity_provider", "totp"]


def test_pending_second_factor_restarts_with_the_organization(client, provider, analyst):
    enable(analyst)
    link(analyst)
    sign_in(client, provider, "sub-analyst")
    session = client.session
    pending = session[PENDING_SIGN_IN]
    pending["started"] = time.time() - 3600
    session[PENDING_SIGN_IN] = pending
    session.save()
    response = client.get(VERIFY)
    assert response["Location"] == LOGIN
    assert "Sign in again with your organization, then enter a new code." in messages_of(response)


# --- Refused answers ------------------------------------------------------------------------


def test_answer_is_used_once_and_only_by_its_session(client, provider, analyst):
    link(analyst)
    provider.next_subject = "sub-analyst"
    callback = to_provider(client.get(START))
    other = Client()
    response = other.get(callback)
    assert not other.session.get("_auth_user_id")
    assert single_sign_on.EXPIRED in messages_of(response)
    assert client.get(callback).status_code == 302 and signed_in_as(client) == str(analyst.pk)
    client.logout()
    response = client.get(callback)
    assert not signed_in_as(client) and single_sign_on.EXPIRED in messages_of(response)


def test_wrong_state_and_late_answer_are_refused(client, provider, analyst):
    link(analyst)
    provider.next_subject = "sub-analyst"
    callback = to_provider(client.get(START))
    forged = callback.replace("state=", "state=x")
    response = client.get(forged)
    assert not signed_in_as(client) and single_sign_on.EXPIRED in messages_of(response)
    assert client.get(callback).status_code == 302 and not signed_in_as(client)  # Spent.
    callback = to_provider(client.get(START))
    session = client.session
    pending = session[SSO_PENDING]
    pending["started"] = time.time() - single_sign_on.PENDING_SECONDS - 1
    session[SSO_PENDING] = pending
    session.save()
    response = client.get(callback)
    assert not signed_in_as(client) and single_sign_on.EXPIRED in messages_of(response)


@pytest.mark.parametrize(
    "change",
    [
        {"override": {"aud": "another-client"}},
        {"override": {"aud": ["another-client", CLIENT_ID]}},
        {"override": {"aud": ["another-client", CLIENT_ID], "azp": CLIENT_ID}},
        {"override": {"iss": "https://elsewhere.synthetic.example"}},
        {"override": {"exp": 1_000_000_000}},
        {"override": {"iat": None}},
        {"override": {"nonce": "replayed-nonce"}},
        {"override": {"nonce": None}},
        {"override": {"sub": None}},
        {"unsigned": True},
        {"symmetric": True},
        {"omit_id_token": True},
        {"token_error": "invalid_grant"},
        {"error": "access_denied"},
        {"error": "server_error"},
        {"answer_iss": "https://elsewhere.synthetic.example"},
    ],
    ids=lambda c: next(iter(c)) + ":" + str(next(iter(c.values()))),
)
def test_answers_that_do_not_validate_are_refused(client, provider, analyst, change):
    link(analyst)
    for name, value in change.items():
        setattr(provider, name, value)
    response = sign_in(client, provider, "sub-analyst")
    assert response.status_code == 302 and response["Location"] == LOGIN
    assert not signed_in_as(client)
    shown = messages_of(response)
    assert shown and (
        single_sign_on.REFUSED in shown or "cancelled or not completed" in shown[0]
    ), shown
    assert not SingleSignOnLink.objects.filter(last_used_at__isnull=False).exists()


def test_issuer_parameter_is_required_when_the_provider_announces_it(client, provider, analyst):
    link(analyst)
    provider.metadata_override = {"authorization_response_iss_parameter_supported": True}
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.REFUSED in messages_of(response)
    provider.answer_iss = provider.issuer
    sign_in(client, provider, "sub-analyst")
    assert signed_in_as(client) == str(analyst.pk)


def test_token_signed_by_an_unpublished_key_is_refused(client, provider, analyst):
    from joserfc.jwk import RSAKey

    link(analyst)
    provider.sign_with = RSAKey.generate_key(2048, parameters={"kid": provider.key.kid})
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.REFUSED in messages_of(response)


def test_rotated_provider_keys_are_fetched_again(client, provider, analyst):
    link(analyst)
    sign_in(client, provider, "sub-analyst")
    assert signed_in_as(client)
    client.logout()
    provider.rotate()
    sign_in(client, provider, "sub-analyst")
    assert signed_in_as(client) == str(analyst.pk)


def test_discovery_for_another_issuer_or_no_provider_is_unavailable(client, provider, settings):
    provider.metadata_override = {"issuer": "https://elsewhere.synthetic.example"}
    response = client.get(START)
    assert response["Location"] == LOGIN
    assert single_sign_on.UNAVAILABLE in messages_of(response)
    response = client.get(START)  # Not asked again at once.
    assert single_sign_on.UNAVAILABLE in messages_of(response)
    assert provider.discovery_requests == 1
    settings.OIDC_ISSUER = "http://127.0.0.1:9/realm"  # Nothing listens on the discard port.
    single_sign_on._client.cache_clear()
    response = client.get(START)
    assert single_sign_on.UNAVAILABLE in messages_of(response)


def test_symmetric_algorithms_are_never_allowed(client, provider, analyst):
    provider.metadata_override = {"id_token_signing_alg_values_supported": ["HS256", "none"]}
    link(analyst)
    provider.symmetric = True
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.REFUSED in messages_of(response)
    assert single_sign_on.client().server_metadata["id_token_signing_alg_values_supported"] == [
        "RS256"
    ]


# --- Linking by the owner ---------------------------------------------------------------------


def start_link(client, data):
    return client.post(PAGE, {"action": "link", **data})


def test_owner_links_after_confirming_the_password(provider, analyst):
    owner = Client()
    owner.force_login(analyst)
    elsewhere = Client()
    elsewhere.force_login(analyst)
    page = owner.get(PAGE)
    assert page.status_code == 200 and b"Not linked" in page.content
    # The page leaves for the provider by an ordinary link, so the site's policy is unchanged.
    assert "form-action 'self';" in page["Content-Security-Policy"]
    assert b"Organization sign-in" in owner.get(reverse("accounts:access")).content
    refused = start_link(owner, {"current_password": "wrong-synthetic"})
    assert refused.status_code == 422 and LoginThrottle.objects.get(user=analyst).failures == 1
    before = fresh(analyst)
    provider.next_subject = "sub-new"
    provider.claims = {"sub-new": {"preferred_username": "a.analyst@synthetic.example"}}
    response = owner.get(to_provider(start_link(owner, {"current_password": PASSWORD})))
    assert response.status_code == 302 and response["Location"] == PAGE
    found = SingleSignOnLink.objects.get(user=analyst)
    assert (found.issuer, found.subject) == (provider.issuer, "sub-new")
    assert found.label == "a.analyst@synthetic.example"
    after = fresh(analyst)
    assert after.management_revision == before.management_revision + 1
    assert after.session_epoch == before.session_epoch + 1
    event = AuditEvent.objects.get(action="account.single_sign_on_linked")
    assert event.actor == analyst and event.before["single_sign_on"] is None
    assert event.after["single_sign_on"]["subject"] == "sub-new"
    assert owner.get(PAGE).status_code == 200  # This session continues.
    assert elsewhere.get(PAGE).status_code == 302  # The others end.
    assert provider.authorize_requests[-1]["prompt"] == "login"
    owner.logout()
    assert sign_in(owner, provider, "sub-new").status_code == 302
    assert signed_in_as(owner) == str(analyst.pk)


def test_link_with_two_factor_needs_a_second_factor(provider, analyst):
    device, _codes = enable(analyst)
    owner = Client()
    owner.force_login(analyst)
    response = start_link(owner, {"current_password": PASSWORD})
    assert response.status_code == 422 and not SingleSignOnLink.objects.exists()
    provider.next_subject = "sub-2fa"
    response = start_link(owner, {"current_password": PASSWORD, "otp_code": code(device, 1)})
    owner.get(to_provider(response))
    assert SingleSignOnLink.objects.get(user=analyst).subject == "sub-2fa"


def test_identity_links_to_one_account_only(provider, analyst, manager):
    link(manager, subject="sub-shared")
    owner = Client()
    owner.force_login(analyst)
    provider.next_subject = "sub-shared"
    response = owner.get(to_provider(start_link(owner, {"current_password": PASSWORD})))
    assert single_sign_on.LINKED_ELSEWHERE in messages_of(response)
    assert not SingleSignOnLink.objects.filter(user=analyst).exists()
    assert not AuditEvent.objects.filter(action="account.single_sign_on_linked").exists()


def test_link_refused_after_a_security_change_or_in_another_session(provider, analyst):
    owner = Client()
    owner.force_login(analyst)
    provider.next_subject = "sub-late"
    callback = to_provider(start_link(owner, {"current_password": PASSWORD}))
    user = fresh(analyst)
    user.session_epoch += 1  # A password change elsewhere, say.
    user.save(update_fields=["session_epoch"])
    session = owner.session
    session["account_epoch"] = user.session_epoch  # Keep this session alive for the check.
    session.save()
    response = owner.get(callback)
    assert single_sign_on.CHANGED in messages_of(response)
    assert not SingleSignOnLink.objects.exists()

    callback = to_provider(start_link(owner, {"current_password": PASSWORD}))
    stranger = Client()
    stranger.force_login(make_user("other.sso", ["analyst"]))
    response = stranger.get(callback)
    assert single_sign_on.EXPIRED in messages_of(response)
    owner.logout()
    response = owner.get(callback)
    assert not SingleSignOnLink.objects.exists()


def test_already_linked_owner_must_unlink_first(provider, analyst):
    link(analyst)
    owner = Client()
    owner.force_login(analyst)
    response = start_link(owner, {"current_password": PASSWORD})
    assert response.status_code == 422
    assert b"The link changed meanwhile" in response.content


def test_owner_unlinks(provider, analyst):
    link(analyst)
    owner = Client()
    owner.force_login(analyst)
    page = owner.get(PAGE)
    assert b"analyst@synthetic.example" in page.content
    response = owner.post(PAGE, {"action": "unlink", "current_password": "wrong-synthetic"})
    assert response.status_code == 422 and SingleSignOnLink.objects.exists()
    response = owner.post(PAGE, {"action": "unlink", "current_password": PASSWORD})
    assert response.status_code == 302 and not SingleSignOnLink.objects.exists()
    event = AuditEvent.objects.get(action="account.single_sign_on_unlinked")
    assert event.before["single_sign_on"]["subject"] == "sub-analyst"
    assert event.after["single_sign_on"] is None
    other = Client()
    response = sign_in(other, provider, "sub-analyst")
    assert single_sign_on.NOT_LINKED in messages_of(response)


def test_link_from_another_provider_is_shown_and_does_not_sign_in(provider, analyst):
    SingleSignOnLink.objects.create(
        user=analyst,
        issuer="https://old.synthetic.example",
        subject="sub-analyst",
        label="old",
        created_at=single_sign_on.timezone.now(),
    )
    owner = Client()
    owner.force_login(analyst)
    assert b"made with another identity provider" in owner.get(PAGE).content
    admin = Client()
    admin.force_login(make_user("admin.sso", ["admin"]))
    detail = admin.get(reverse("accounts:user_detail", args=[analyst.pk]))
    assert b"so it no longer signs in" in detail.content
    response = sign_in(Client(), provider, "sub-analyst")
    assert single_sign_on.NOT_LINKED in messages_of(response)


def test_demonstration_account_cannot_link(provider, analyst):
    get_user_model().objects.filter(pk=analyst.pk).update(credentials_locked=True)
    owner = Client()
    owner.force_login(analyst)
    assert b"shared demonstration account" in owner.get(PAGE).content
    response = start_link(owner, {"current_password": PASSWORD})
    assert response.status_code == 403 and not SingleSignOnLink.objects.exists()


# --- Administrator --------------------------------------------------------------------------


def test_administrator_removes_a_link_with_a_signature(provider, analyst, manager):
    admin = Client()
    admin.force_login(manager)
    url = reverse("accounts:user_action", args=[analyst.pk, "remove_single_sign_on"])
    detail = admin.get(reverse("accounts:user_detail", args=[analyst.pk]))
    assert url.encode() not in detail.content and b"Not linked" in detail.content
    link(analyst)
    detail = admin.get(reverse("accounts:user_detail", args=[analyst.pk]))
    assert url.encode() in detail.content and b"analyst@synthetic.example" in detail.content
    response = admin.post(
        url,
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic: person left the organization",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302 and not SingleSignOnLink.objects.exists()
    event = AuditEvent.objects.get(action="account.remove_single_sign_on")
    assert event.actor == manager and event.before["single_sign_on"]["label"]
    assert ElectronicSignature.objects.get(audit_event=event).meaning == "account_authorized"
    assert "not linked" in admin.get(url).context["unavailable"]

    link(manager, subject="sub-manager")
    own = reverse("accounts:user_action", args=[manager.pk, "remove_single_sign_on"])
    assert "Unlink your own" in admin.get(own).context["unavailable"]
    response = admin.post(
        own,
        {
            "revision": fresh(manager).management_revision,
            "reason": "Synthetic",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 403 and SingleSignOnLink.objects.filter(user=manager).exists()


def test_sign_in_through_the_provider_is_recorded_on_signatures(provider, manager, analyst):
    link(manager, subject="sub-manager")
    admin = Client()
    sign_in(admin, provider, "sub-manager")
    link(analyst)
    response = admin.post(
        reverse("accounts:user_action", args=[analyst.pk, "remove_single_sign_on"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    signature = ElectronicSignature.objects.get(audit_event__action="account.remove_single_sign_on")
    assert signature.authentication_context["sign_in_factors"] == ["identity_provider"]
    assert signature.authentication_context["components"] == ["username", "pin"]


# --- Review findings ---------------------------------------------------------------------


def test_discovery_cannot_switch_off_checks_or_client_settings(client, provider, analyst):
    link(analyst)
    provider.metadata_override = {
        "_checked": True,
        "scope": "openid",
        "code_challenge_method": "plain",
        "id_token_signing_alg_values_supported": ["none", "RS256"],
    }
    response = client.get(START)
    params = parse_qs(urlsplit(response["Location"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["openid email profile"]
    metadata = single_sign_on.client().server_metadata
    assert "_checked" not in metadata and "scope" not in metadata
    client.get(START)  # A new request replaces the pending one.
    provider.unsigned = True
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.REFUSED in messages_of(response)


def test_discovery_is_fetched_once_and_only_checked_keys_are_used(client, provider, analyst):
    link(analyst)
    provider.metadata_override = {"verify": False, "proxies": {"https": "http://x.invalid"}}
    for _ in range(3):
        sign_in(client, provider, "sub-analyst")
        assert signed_in_as(client) == str(analyst.pk)
        client.logout()
    assert provider.discovery_requests == 1
    metadata = single_sign_on.client().server_metadata
    assert set(metadata) <= set(single_sign_on.METADATA_KEYS) | {"jwks"}


@pytest.mark.parametrize("key", ["authorization_endpoint", "token_endpoint", "jwks_uri"])
def test_discovery_endpoints_must_use_https(client, provider, key):
    provider.metadata_override = {key: "http://idp.synthetic.example/endpoint"}
    response = client.get(START)
    assert response["Location"] == LOGIN
    assert single_sign_on.UNAVAILABLE in messages_of(response)


def test_unreachable_provider_spends_no_second_factor(provider, analyst, settings):
    _device, codes = enable(analyst)
    settings.OIDC_ISSUER = "http://127.0.0.1:9/realm"
    single_sign_on._client.cache_clear()
    owner = Client()
    owner.force_login(analyst)
    response = start_link(owner, {"current_password": PASSWORD, "otp_code": codes[0]})
    assert response.status_code == 422 and b"could not be reached" in response.content
    assert two_factor_codes_left(analyst) == len(codes)


def two_factor_codes_left(user):
    from accounts.models import RecoveryCode

    return RecoveryCode.objects.filter(user=user, used_at=None).count()


def test_earlier_authentication_is_refused_with_prompt_login(client, provider, analyst):
    link(analyst)
    provider.override = {"auth_time": int(time.time()) - 3600}
    response = sign_in(client, provider, "sub-analyst")
    assert not signed_in_as(client) and single_sign_on.REFUSED in messages_of(response)
    provider.override = {"auth_time": int(time.time())}
    sign_in(client, provider, "sub-analyst")
    assert signed_in_as(client) == str(analyst.pk)


def test_unverified_email_is_not_the_label(provider, analyst):
    owner = Client()
    owner.force_login(analyst)
    provider.next_subject = "sub-email"
    provider.claims = {"sub-email": {"email": "boss@synthetic.example", "email_verified": False}}
    owner.get(to_provider(start_link(owner, {"current_password": PASSWORD})))
    found = SingleSignOnLink.objects.get(user=analyst)
    assert found.label == "sub-email"
    assert b"Subject sub-email" in owner.get(PAGE).content


def test_password_resets_and_changes_do_not_hide_a_link(provider, analyst, manager):
    link(analyst)
    owner = Client()
    owner.force_login(analyst)
    response = owner.post(
        reverse("accounts:password_change"),
        {
            "current_password": PASSWORD,
            "password": "Synthetic-new-pass-2026!x",
            "password_confirmation": "Synthetic-new-pass-2026!x",
            "reason": "Synthetic rotation",
        },
    )
    assert response.status_code == 302
    shown = messages_of(response)
    assert any(
        "still linked to the organization account analyst@synthetic.example (subject "
        "sub-analyst, linked " in m
        for m in shown
    )
    assert SingleSignOnLink.objects.filter(user=analyst).exists()

    admin = Client()
    admin.force_login(manager)
    response = admin.post(
        reverse("accounts:user_action", args=[analyst.pk, "reset_password"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic: suspected compromise",
            "signature_username": manager.username,
            "pin": PIN,
            "temporary_password": "Synthetic-temp-pass-2026!y",
            "password_confirmation": "Synthetic-temp-pass-2026!y",
        },
    )
    assert response.status_code == 302, response.content[:300]
    assert not SingleSignOnLink.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.get(action="account.reset_password")
    assert event.before["single_sign_on"] and event.after["single_sign_on"] is None
    response = sign_in(Client(), provider, "sub-analyst")
    assert single_sign_on.NOT_LINKED in messages_of(response)


def test_already_linked_is_refused_before_a_code_is_spent(provider, analyst):
    _device, codes = enable(analyst)
    link(analyst)
    with pytest.raises(single_sign_on.ValidationError, match="already linked"):
        single_sign_on.begin_link(actor=fresh(analyst), current_password=PASSWORD, code=codes[0])
    assert two_factor_codes_left(analyst) == len(codes)


def test_two_factor_reset_removes_the_link(provider, analyst, manager):
    enable(analyst)
    link(analyst)
    admin = Client()
    admin.force_login(manager)
    response = admin.post(
        reverse("accounts:user_action", args=[analyst.pk, "reset_two_factor"]),
        {
            "revision": fresh(analyst).management_revision,
            "reason": "Synthetic lost phone, identity verified",
            "signature_username": manager.username,
            "pin": PIN,
        },
    )
    assert response.status_code == 302
    assert not SingleSignOnLink.objects.filter(user=analyst).exists()
    event = AuditEvent.objects.get(action="account.reset_two_factor")
    assert event.before["single_sign_on"] and event.after["single_sign_on"] is None
