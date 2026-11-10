import pytest
from django.contrib.auth.models import Group
from django.templatetags.static import static
from django.urls import reverse

pytestmark = pytest.mark.django_db
FRAGMENT = {"HTTP_X_PAGEDOCS": "fragment"}


@pytest.fixture
def analyst(django_user_model):
    user = django_user_model.objects.create_user("analyst.test", password="synthetic-pass-1")
    user.groups.add(Group.objects.get_or_create(name="analyst")[0])
    return user


def doc_url(path):
    return f"{reverse('pagedocs:doc')}?path={path}"


def test_fragment_for_documented_page(client, analyst):
    client.force_login(analyst)
    response = client.get(doc_url("/"), **FRAGMENT)
    assert response.status_code == 200
    body = response.content.decode()
    assert 'data-pagedocs-for="quality:lot_list"' in body
    assert "Material lots" in body and "<h3" in body
    assert "<html" not in body


def test_fragment_resolves_parameterised_paths(client, analyst):
    client.force_login(analyst)
    response = client.get(doc_url("/lots/999/?q=x"), **FRAGMENT)
    assert 'data-pagedocs-for="quality:lot_detail"' in response.content.decode()


@pytest.mark.parametrize(
    "path", ["/no-such-page/", "https://evil.example/", "//evil/", "", "/\\evil"]
)
def test_unknown_or_foreign_paths_are_not_documented(client, analyst, path):
    client.force_login(analyst)
    response = client.get(doc_url(path), **FRAGMENT)
    assert response.status_code == 404
    assert "Not documented yet" in response.content.decode()


def test_fragment_requires_sign_in(client):
    response = client.get(doc_url("/"), **FRAGMENT)
    assert response.status_code == 403
    assert "Material lots" not in response.content.decode()


def test_full_page_fallback(client, analyst):
    assert client.get(doc_url("/")).status_code == 302  # signed out: sign-in redirect
    client.force_login(analyst)
    response = client.get(doc_url("/rules/"))
    body = response.content.decode()
    assert response.status_code == 200 and "<html" in body
    assert 'href="/rules/"' in body and "Rule sets" in body


def test_post_is_rejected(client, analyst):
    client.force_login(analyst)
    assert client.post(doc_url("/")).status_code == 405


def test_shell_contains_toggle_and_panel(client, analyst):
    """Integration check: base template includes the pagedocs head, button and panel."""
    client.force_login(analyst)
    body = client.get("/").content.decode()
    assert "data-pagedocs-toggle" in body and 'aria-controls="pagedocs-panel"' in body
    assert 'id="pagedocs-panel"' in body and 'role="separator"' in body
    for asset in ("pagedocs/pagedocs-init.js", "pagedocs/pagedocs.js", "pagedocs/pagedocs.css"):
        assert static(asset) in body, asset  # hashed under the production manifest
