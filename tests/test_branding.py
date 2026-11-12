"""Product name and the AGPL-3.0 section 13 source-code link on every page."""

import re

import pytest
from django.contrib.auth.models import Group
from django.test import override_settings

pytestmark = pytest.mark.django_db

SOURCE_LINK = re.compile(
    r'<footer class="vr-app-footer[^"]*">.*?<a href="(?P<href>[^"]+)"[^>]*>Source code</a>',
    re.S,
)


def footer_source_url(response):
    match = SOURCE_LINK.search(response.content.decode())
    assert match, "page has no application footer with a Source code link"
    return match["href"]


def test_login_page_links_to_source_code(client):
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert footer_source_url(response) == "https://github.com/openbga/fresh-coa-lims"
    assert "<title>Sign in · OpenBGA Fresh CoA LIMS</title>" in response.content.decode()


def test_workspace_page_shows_brand_and_source_link_outside_main(client, django_user_model):
    user = django_user_model.objects.create_user("brand-auditor")
    user.groups.add(Group.objects.get_or_create(name="auditor")[0])
    client.force_login(user)
    response = client.get("/audit/")
    assert response.status_code == 200
    body = response.content.decode()
    assert footer_source_url(response) == "https://github.com/openbga/fresh-coa-lims"
    assert "OpenBGA Fresh CoA LIMS" in body
    # The footer must stay outside <main>.
    assert body.index('class="vr-app-footer"') > body.index("</main>")


@override_settings(SOURCE_CODE_URL="https://example.invalid/modified-qual")
def test_source_link_follows_deployment_setting(client):
    response = client.get("/accounts/login/")
    assert footer_source_url(response) == "https://example.invalid/modified-qual"
