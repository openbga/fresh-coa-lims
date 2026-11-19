"""Remote select lookups (core/lookups.py): one permission-scoped endpoint for growing lists.

Every read is authorized on the server by laboratory role: the lookup offers what a laboratory
role may read, an account without a role (even a superuser) or an inactive one gets nothing,
and an anonymous request is sent to sign in. The form field stays the validator.
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from catalog import forms as catalog_forms
from catalog.models import Material
from core.lookups import LOOKUPS, RemoteSelect
from core.models import RuleSet
from impact.forms import StartForm
from laboratory.forms import QualificationForm, TrainingForm
from planning import forms as planning_forms
from quality.forms import LotForm
from quality.models import Lot
from reporting.forms import LotPickForm
from sampling.forms import AssignForm, PlanForm
from stability.forms import HoldForm, ObligationForm, ProtocolForm, ReserveForm, StudyForm
from suppliers.forms import MaterialChoiceForm
from validation.forms import UseAcceptanceForm

pytestmark = pytest.mark.django_db

ROLES = ("analyst", "reviewer", "quality", "auditor", "admin")


@pytest.fixture
def people(django_user_model):
    found = {}
    for role in ROLES:
        user = django_user_model.objects.create_user(f"syn-{role}", first_name="Synthetic")
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        found[role] = user
    found["roleless"] = django_user_model.objects.create_user(
        "syn-roleless", is_staff=True, is_superuser=True
    )
    inactive = django_user_model.objects.create_user("syn-inactive", is_active=False)
    inactive.groups.add(Group.objects.get_or_create(name="quality")[0])
    found["inactive"] = inactive
    return found


@pytest.fixture
def materials(people):
    return [
        Material.objects.create(
            code=f"syn-mat-{n:02}",
            name=f"Synthetic material {n}",
            kind="raw_material",
            created_by=people["quality"],
        )
        for n in range(1, 26)
    ]


def lookup(client, name, **params):
    return client.get(reverse("core:lookup", args=[name]), params)


@pytest.mark.parametrize("role", ROLES)
def test_every_laboratory_role_reads_a_lookup(client, people, materials, role):
    client.force_login(people[role])
    response = lookup(client, "materials")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 20 and data["more"] is True  # one page of the page size
    assert data["results"][0] == {
        "value": str(materials[0].pk),
        "text": "syn-mat-01 · Synthetic material 1",
    }


@pytest.mark.parametrize("who", ["roleless", "inactive"])
def test_account_without_an_active_laboratory_role_gets_nothing(client, people, materials, who):
    client.force_login(people[who])
    response = lookup(client, "materials")
    # An inactive account's session is ended by the session middleware (a sign-in redirect);
    # either way no option is sent.
    assert response.status_code == (403 if who == "roleless" else 302)
    assert "syn-mat" not in response.content.decode()


def test_anonymous_request_is_sent_to_sign_in(client, materials):
    response = lookup(client, "materials")
    assert response.status_code == 302 and reverse("login") in response["Location"]


def test_unknown_lookup_is_not_found_and_only_get_is_allowed(client, people):
    client.force_login(people["analyst"])
    assert lookup(client, "no-such-list").status_code == 404
    assert client.post(reverse("core:lookup", args=["materials"])).status_code == 405


def test_search_matches_every_word_and_pages(client, people, materials):
    client.force_login(people["analyst"])
    data = lookup(client, "materials", q="synthetic 2").json()
    texts = [item["text"] for item in data["results"]]
    assert texts == [m.__str__() for m in materials if "2" in m.name]
    assert data["more"] is False
    second = lookup(client, "materials", page=2).json()
    assert [item["text"] for item in second["results"]] == [str(m) for m in materials[20:]]
    assert second["more"] is False
    assert lookup(client, "materials", page=9).json() == {"results": [], "more": False}
    assert (
        lookup(client, "materials", page="x").json()["results"][0]["text"].startswith("syn-mat-01")
    )
    assert lookup(client, "materials", q="no match at all").json()["results"] == []


def test_lot_lookups_offer_only_their_states(client, people):
    rules = RuleSet.objects.create(
        code="syn-lookup",
        segment="chemical",
        author=people["quality"],
        status="approved",
        effective_from=timezone.now(),
        effective_until=timezone.now() + timezone.timedelta(days=30),
        policy={
            "required_tests": ["identity"],
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
    )
    for state in ("quarantine", "released", "rejected", "cancelled"):
        evidence = {} if state in ("quarantine", "released") else {"decision": {}, "schema": ""}
        Lot.objects.create(
            number=f"SYN-{state.upper()}",
            material="Synthetic powder",
            rules=rules,
            created_by=people["analyst"],
            state=state,
            disposition_evidence=evidence,
        )
    client.force_login(people["auditor"])

    def numbers(name):
        return {item["text"] for item in lookup(client, name).json()["results"]}

    assert numbers("released-lots") == {"SYN-RELEASED"}
    assert numbers("study-lots") == {"SYN-QUARANTINE", "SYN-RELEASED"}
    assert numbers("lots") == {"SYN-QUARANTINE", "SYN-RELEASED", "SYN-REJECTED"}


def test_user_lookups_never_offer_inactive_accounts(client, people):
    client.force_login(people["quality"])
    names = {item["text"] for item in lookup(client, "active-users").json()["results"]}
    assert "syn-inactive" not in names and "syn-analyst" in names
    owners = {item["text"] for item in lookup(client, "owner-candidates").json()["results"]}
    assert "Synthetic (syn-quality)" in owners
    assert not {"syn-inactive", "syn-roleless"} & {o.split()[-1].strip("()") for o in owners}


def test_remote_select_renders_only_the_selected_option(people, materials):
    chosen = materials[3]
    form = PlanForm(initial={"material": chosen.pk})
    html = " ".join(str(form["material"]).split()).replace(" >", ">")
    assert f'data-vr-lookup="{reverse("core:lookup", args=["materials"])}"' in html
    assert html.count("<option") == 2  # the empty choice and the current value
    assert f'value="{chosen.pk}" selected>{chosen}</option>' in html
    # A submitted value that is not a key renders no option, and the field rejects it.
    bound = PlanForm(data={"material": "not-a-key"})
    assert str(bound["material"]).count("<option") == 1
    assert not bound.is_valid() and "material" in bound.errors


def test_field_still_validates_against_its_own_queryset(people, materials):
    released_only = LotPickForm(data={"lot": "999999"})
    assert not released_only.is_valid() and "lot" in released_only.errors


# Each form field that opts into a lookup, with the lookup it names. The lookup's source must
# offer exactly what the field validates, or a user would be offered a choice the form refuses
# (or miss one it accepts).
REMOTE_FIELDS = [
    (lambda: catalog_forms.SpecificationForm(), "material"),
    (lambda: catalog_forms.TestLineForm(), "method"),
    (lambda: PlanForm(), "material"),
    (lambda: AssignForm(), "material"),
    (lambda: MaterialChoiceForm(), "material"),
    (lambda: LotForm(), "supplier"),
    (lambda: LotPickForm(), "lot"),
    (lambda: QualificationForm(), "user"),
    (lambda: QualificationForm(), "training"),
    (lambda: TrainingForm(), "trainee"),
    (lambda: UseAcceptanceForm(methods={}), "process_owner"),
    (lambda: UseAcceptanceForm(methods={}), "system_owner"),
    (lambda: ProtocolForm(), "specification"),
    (lambda: StudyForm(), "lot"),
    (lambda: ReserveForm(), "lot"),
    (lambda: ObligationForm(with_lot=True), "lot"),
    (lambda: HoldForm(), "lot"),
    (lambda: StartForm(), "equipment"),
    (lambda: StartForm(), "reagent_lot"),
    (lambda: StartForm(), "supplier"),
    (lambda: StartForm(), "contract_laboratory"),
    (lambda: planning_forms.PlanForm(), "analyst"),
    (lambda: planning_forms.PlanForm(), "equipment"),
]


def comparable(queryset):
    """The records a queryset selects, whatever its ordering or joins."""
    return str(queryset.order_by().values("pk").query)


@pytest.mark.parametrize("make, name", REMOTE_FIELDS)
def test_lookup_offers_what_the_field_validates(make, name):
    field = make().fields[name]
    assert isinstance(field.widget, RemoteSelect)
    entry = LOOKUPS[field.widget.lookup]
    assert comparable(entry.source()) == comparable(field.queryset)
    obj = field.queryset.model()
    if hasattr(obj, "code"):
        obj.code, obj.name, obj.title = "c", "n", "t"
    if field.widget.lookup != "specifications":
        assert entry.label(obj) == field.label_from_instance(obj)


def test_every_registered_lookup_is_used_and_authorized():
    used = {make().fields[name].widget.lookup for make, name in REMOTE_FIELDS}
    assert used == set(LOOKUPS)
    assert all(set(entry.roles) == set(ROLES) for entry in LOOKUPS.values())
