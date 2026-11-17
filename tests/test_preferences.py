"""Per-user presentation preferences (core/preferences.py): kept on the server, never shared.

Lab workstations are shared, so a column layout, a list's page size and sort and the sidebar's
state follow the signed-in person, not the browser. A preference never widens what anyone sees.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.template import Context, Template
from django.test import Client, RequestFactory
from django.urls import reverse

from core.models import UserPreference
from core.preferences import MAX_PREFERENCES, clean

pytestmark = pytest.mark.django_db

LAYOUT = {"order": ["asset", "status"], "hidden": ["category"]}


@pytest.fixture
def person(django_user_model):
    def make(username, role="analyst"):
        user = django_user_model.objects.create_user(username)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        return user

    return make


def post(client, key, value):
    return client.post(
        reverse("core:preference"),
        json.dumps({"key": key, "value": value}),
        content_type="application/json",
    )


def page_prefs(client):
    """What {% client_preferences %} hands to the page's scripts for the signed-in user."""
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.get(pk=client.session["_auth_user_id"])
    request.session = client.session
    html = Template("{% load preferences %}{% client_preferences %}").render(
        Context({"request": request})
    )
    opening = '<script id="vr-preferences" type="application/json">'
    assert html.startswith(opening) and html.endswith("</script>")
    return json.loads(html[len(opening) : -len("</script>")])


def test_endpoint_is_the_documented_url():
    assert reverse("core:preference") == "/preferences/"  # static/js/preferences.js


def test_layout_is_saved_per_user_and_isolated(client, person):
    first, second = person("syn-pref-a"), person("syn-pref-b")
    client.force_login(first)
    assert post(client, "grid:laboratory.equipment:v1", LAYOUT).status_code == 204
    assert page_prefs(client) == {"grid:laboratory.equipment:v1": LAYOUT}
    client.force_login(second)
    assert page_prefs(client) == {}  # everyone else keeps the defaults
    assert not UserPreference.objects.filter(user=second).exists()
    client.force_login(first)
    assert post(client, "grid:laboratory.equipment:v1", None).status_code == 204  # reset
    assert not UserPreference.objects.filter(user=first).exists()


def test_bad_values_are_refused_and_stored_junk_falls_back(client, person):
    user = person("syn-pref-c")
    client.force_login(user)
    assert post(client, "grid:laboratory.equipment:v1", {"order": "asset"}).status_code == 400
    assert post(client, "grid:x:v1", {"order": ["<b>"], "hidden": []}).status_code == 400
    # Page size and sort are set by the server from the list's own query string.
    assert post(client, "page:laboratory:equipment_list", {"per_page": 50}).status_code == 400
    assert post(client, "theme", "dark").status_code == 400
    refused = post(client, "<script>", 1)
    assert refused.status_code == 400 and refused["Content-Type"].startswith("text/plain")
    url = reverse("core:preference")
    assert client.post(url, "not json", content_type="text/plain").status_code == 400
    assert client.post(url, json.dumps([1]), content_type="application/json").status_code == 400
    too_large = json.dumps({"key": "nav.collapsed", "value": True, "pad": "x" * 9000})
    assert client.post(url, too_large, content_type="application/json").status_code == 400
    assert client.get(url).status_code == 405
    assert not UserPreference.objects.exists()
    # A value stored in an older format is ignored, not trusted (read again at sign-in).
    UserPreference.objects.create(user=user, key="grid:laboratory.equipment:v1", value=["a"])
    client.logout()
    client.force_login(user)
    assert page_prefs(client) == {}


def test_number_of_saved_preferences_is_bounded(client, person):
    user = person("syn-pref-d")
    UserPreference.objects.bulk_create(
        UserPreference(user=user, key=f"grid:g{n}:v1", value=LAYOUT) for n in range(MAX_PREFERENCES)
    )
    client.force_login(user)
    assert post(client, "grid:one-more:v1", LAYOUT).status_code == 400
    assert post(client, "grid:g1:v1", {"order": [], "hidden": []}).status_code == 204  # update


def test_clean_accepts_only_the_declared_shapes():
    assert clean("grid:a.b:v1", LAYOUT) == LAYOUT
    assert clean("grid:a.b:v1", {**LAYOUT, "extra": 1}) is None
    assert clean("page:laboratory:equipment_list", {"per_page": 100, "sort": "-asset"}) == {
        "per_page": 100,
        "sort": "-asset",
    }
    assert clean("page:laboratory:equipment_list", {"per_page": True}) is None
    assert clean("page:laboratory:equipment_list", {"per_page": 7}) is None
    assert clean("page:laboratory:equipment_list", {"sort": "x; drop"}) is None
    assert clean("nav.collapsed", True) is True
    assert clean("nav.collapsed", "yes") is None
    assert clean("other", True) is None
    assert clean("pagedocs.open", False) is False
    assert clean("pagedocs.width", 420) == 420
    assert clean("pagedocs.width", 279) is None and clean("pagedocs.width", 961) is None
    assert clean("pagedocs.width", True) is None and clean("pagedocs.width", "420") is None


def test_saving_needs_sign_in_and_a_csrf_token(person):
    anonymous = Client(enforce_csrf_checks=True)
    response = post(anonymous, "nav.collapsed", True)
    assert response.status_code in (302, 403) and not UserPreference.objects.exists()
    user = person("syn-pref-e")
    browser = Client(enforce_csrf_checks=True)
    browser.force_login(user)
    assert post(browser, "nav.collapsed", True).status_code == 403  # no token: refused
    browser.get(reverse("core:pin"))  # any page sets the CSRF cookie
    token = browser.cookies["csrftoken"].value
    response = browser.post(
        reverse("core:preference"),
        json.dumps({"key": "nav.collapsed", "value": True}),
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 204
    assert UserPreference.objects.get(user=user, key="nav.collapsed").value is True


def test_sidebar_state_tag(client, person):
    user = person("syn-pref-f", "reviewer")
    client.force_login(user)
    assert post(client, "nav.collapsed", True).status_code == 204
    request = RequestFactory().get("/")
    request.user, request.session = user, client.session
    rendered = Template(
        '{% load preferences %}{% preference "nav.collapsed" as collapsed %}{{ collapsed }}'
    ).render(Context({"request": request}))
    assert rendered == "True"
    assert page_prefs(client) == {"nav.collapsed": True}


def test_a_change_shows_on_the_next_page_of_every_session(client, person):
    user = person("syn-pref-g")
    client.force_login(user)
    other = Client()
    other.force_login(user)  # the same person on another workstation
    assert post(client, "nav.collapsed", True).status_code == 204
    assert page_prefs(other) == {"nav.collapsed": True}
    UserPreference.objects.filter(user=user).delete()
    assert page_prefs(client) == {}


def test_settings_saved_at_the_same_moment_are_all_kept(client, person):
    user = person("syn-pref-h")
    client.force_login(user)
    # Two requests of one page (open the panel, set its width) each save their own key.
    assert post(client, "pagedocs.open", True).status_code == 204
    assert post(client, "pagedocs.width", 500).status_code == 204
    assert page_prefs(client) == {"pagedocs.open": True, "pagedocs.width": 500}


def test_page_size_and_sort_persist_per_user_and_list(client, person):
    user, other = person("syn-pref-j"), person("syn-pref-k")
    client.force_login(user)
    url = reverse("laboratory:equipment_list")
    assert client.get(url).context["page_obj"].paginator.per_page == 25  # default
    client.get(url, {"per_page": 50, "sort": "-asset"})
    response = client.get(url)  # no parameters: the saved ones apply
    assert response.context["page_obj"].paginator.per_page == 50
    assert response.wsgi_request.GET["sort"] == "-asset"
    assert client.get(url, {"per_page": 100}).context["page_obj"].paginator.per_page == 100
    assert client.get(url).context["page_obj"].paginator.per_page == 100
    client.get(url, {"per_page": 9})  # not a page size: never saved
    assert UserPreference.objects.get(user=user, key="page:laboratory:equipment_list").value == {
        "per_page": 100,
        "sort": "-asset",
    }
    client.force_login(other)
    assert client.get(url).context["page_obj"].paginator.per_page == 25


def test_a_preference_never_opens_a_page(client, person):
    user = person("syn-pref-l")
    user.groups.clear()  # no laboratory role
    UserPreference.objects.create(
        user=user, key="page:laboratory:equipment_list", value={"per_page": 100}
    )
    client.force_login(user)
    assert client.get(reverse("laboratory:equipment_list")).status_code == 403


def test_documentation_panel_state_is_a_personal_setting(client, person):
    user = person("syn-pref-m")
    client.force_login(user)
    assert post(client, "pagedocs.open", True).status_code == 204
    assert post(client, "pagedocs.width", 512).status_code == 204
    assert post(client, "pagedocs.width", 5000).status_code == 400
    assert page_prefs(client) == {"pagedocs.open": True, "pagedocs.width": 512}
    client.force_login(person("syn-pref-n"))
    assert page_prefs(client) == {}
