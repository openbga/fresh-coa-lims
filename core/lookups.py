"""Remote option lookups for large or growing choice lists (the remote select).

The same pattern as Django admin's autocomplete: a `RemoteSelect` renders only the selected
option(s); static/js/controls.js loads the rest page by page from `core:lookup` as the user types.
Each registered `Lookup` builds its queryset for the request, so every read is authorized on the
server by laboratory role (AGENTS.md rule 3): an inactive account or one without a laboratory role
is refused, whatever its Django staff or superuser flags. The form's ModelChoiceField stays the
validator: a lookup only offers options, and a value the field's own queryset rejects is still
rejected on submit.

Opt in per field with the widget only, keeping the field's queryset as it is:
`forms.ModelChoiceField(queryset=Material.objects.all(), widget=RemoteSelect("materials"))`.
The lookup's `source` must offer the same records as that queryset (tests/test_lookups.py checks
each form that uses one). Short configuration lists and lists scoped to one record stay inline.
"""

from dataclasses import dataclass
from functools import reduce
from operator import or_

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

from core.services import require_role

# Every laboratory role reads laboratory records (the READ_ROLES of each module).
LAB_READ_ROLES = ("analyst", "reviewer", "quality", "admin", "auditor")
MAX_QUERY = 100  # characters of search text considered


def user_label(user):
    name = user.get_full_name()
    return f"{name} ({user.get_username()})" if name else user.get_username()


@dataclass(frozen=True)
class Lookup:
    """One remote option list.

    source: callable() -> QuerySet of every record the form field offers (and validates).
    search_fields: ORM paths matched with icontains; every typed word must match one of them.
    ordering: ORM ordering of the options.
    label: callable(obj) -> option text; the same as the form field's label_from_instance.
    roles: laboratory roles that may read the list.
    """

    name: str
    source: object
    search_fields: tuple
    ordering: tuple
    label: object = str
    page_size: int = 20
    roles: tuple = LAB_READ_ROLES

    def queryset(self, request):
        """The records this request may choose from; PermissionDenied for anyone else."""
        require_role(request.user, *self.roles)
        return self.source()


LOOKUPS = {}


def register(lookup):
    if lookup.name in LOOKUPS:
        raise ValueError(f"Lookup {lookup.name!r} is already registered.")
    LOOKUPS[lookup.name] = lookup
    return lookup


def _model(label):
    return apps.get_model(label)


def _lots(**exclude):
    return lambda: _model("quality.Lot").objects.exclude(**exclude)


LOT_SEARCH = ("number", "material")


def _planning():
    from planning import services

    return services


def _training():
    from laboratory import forms

    return forms


def _trending():
    from trending import services

    return services


def _owner_candidates():
    from validation.services import owner_candidates

    return owner_candidates()


register(
    Lookup(
        "materials",
        lambda: _model("catalog.Material").objects.all(),
        ("code", "name"),
        ("code", "pk"),
    )
)
register(
    Lookup(
        "methods",
        lambda: _model("catalog.Method").objects.all(),
        ("code", "title"),
        ("code", "pk"),
    )
)
register(
    Lookup(
        "specifications",
        lambda: _model("catalog.Specification").objects.select_related("material"),
        ("code", "title", "material__code", "material__name", "scope"),
        ("code", "pk"),
        label=lambda spec: (
            f"{spec.code} · {spec.title} ({spec.material.code}, {spec.get_stage_display()}, "
            f"scope {spec.scope})"
        ),
    )
)
register(
    Lookup(
        "suppliers",
        lambda: _model("suppliers.Supplier").objects.all(),
        ("code", "name"),
        ("code", "pk"),
    )
)
register(
    Lookup(
        "released-lots",
        lambda: _model("quality.Lot").objects.filter(state="released"),
        LOT_SEARCH,
        ("number", "pk"),
    )
)
register(Lookup("lots", _lots(state="cancelled"), LOT_SEARCH, ("number", "pk")))
register(
    Lookup(
        "equipment",
        lambda: _model("laboratory.Equipment").objects.all(),
        ("asset_id", "description", "category"),
        ("asset_id", "pk"),
        label=lambda item: f"{item.asset_id} · {item.description}",
    )
)
register(
    Lookup(
        "instruments-in-service",
        lambda: _planning().instruments(),
        ("asset_id", "description", "category"),
        ("asset_id", "pk"),
        label=lambda item: f"{item.asset_id} · {item.description}",
    )
)
register(
    Lookup(
        "reagent-lots",
        lambda: _model("laboratory.ReagentLot").objects.all(),
        ("identifier", "name", "lot_number"),
        ("identifier", "pk"),
        label=lambda item: f"{item.identifier} · {item.name}",
    )
)
register(
    Lookup(
        "training-records",
        lambda: _training().supporting_training(),
        (
            "activity",
            "document_ref",
            "trainee__username",
            "trainee__first_name",
            "trainee__last_name",
        ),
        ("-completed_on", "-pk"),
        label=lambda record: _training().training_label(record),
    )
)
register(
    Lookup(
        "contract-laboratories",
        lambda: _model("laboratory.ContractLaboratory").objects.all(),
        ("code", "name"),
        ("code", "pk"),
        label=lambda item: f"{item.code} · {item.name}",
    )
)
register(
    Lookup(
        "study-lots",
        lambda: _model("quality.Lot").objects.exclude(state__in=["rejected", "cancelled"]),
        LOT_SEARCH,
        ("number", "pk"),
    )
)
register(
    Lookup(
        "trend-lines",
        lambda: _trending().chart_lines(uncharted=True),
        (
            "code",
            "name",
            "specification_revision__specification__code",
            "specification_revision__specification__material__code",
            "specification_revision__specification__material__name",
        ),
        ("specification_revision__specification__material__code", "code", "pk"),
        label=lambda line: _trending().line_label(line),
    )
)
register(
    Lookup(
        "impact-assessments",
        lambda: _model("impact.Assessment").objects.exclude(state="withdrawn"),
        ("title", "description", "quality_reference"),
        ("-started_at", "-pk"),
        label=lambda assessment: f"{assessment.label} · {assessment.title}",
    )
)
register(
    Lookup(
        "active-users",
        lambda: get_user_model().objects.filter(is_active=True),
        ("username", "first_name", "last_name"),
        ("username", "pk"),
    )
)
register(
    Lookup(
        "analysts",
        lambda: _planning().analysts(),
        ("username", "first_name", "last_name"),
        ("username", "pk"),
        label=user_label,
    )
)
register(
    Lookup(
        "owner-candidates",
        _owner_candidates,
        ("username", "first_name", "last_name"),
        ("username", "pk"),
        label=user_label,
    )
)


def search(queryset, fields, text):
    for term in text.split():
        queryset = queryset.filter(reduce(or_, (Q(**{f"{f}__icontains": term}) for f in fields)))
    return queryset


@login_required
@require_GET
def lookup(request, name):
    """JSON page of options: {"results": [{"value", "text"}], "more": bool}."""
    entry = LOOKUPS.get(name)
    if entry is None:
        raise Http404("No such lookup.")
    queryset = entry.queryset(request)  # before anything else: a refusal reveals nothing
    queryset = search(queryset, entry.search_fields, request.GET.get("q", "")[:MAX_QUERY])
    paginator = Paginator(queryset.order_by(*entry.ordering), entry.page_size)
    try:
        page = paginator.page(request.GET.get("page") or 1)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        return JsonResponse({"results": [], "more": False})
    results = [{"value": str(obj.pk), "text": entry.label(obj)} for obj in page]
    return JsonResponse({"results": results, "more": page.has_next()})


class RemoteSelect(forms.Select):
    """A select whose options load from a registered lookup as the user types.

    Renders the empty choice and the selected option(s) only, taken from the form field's own
    queryset, so an edit form or a form returned with errors shows its current value.
    """

    def __init__(self, lookup, attrs=None):
        if lookup not in LOOKUPS:
            raise ValueError(f"Unknown lookup {lookup!r}.")
        super().__init__(attrs)
        self.lookup = lookup

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["data-vr-lookup"] = reverse("core:lookup", args=[self.lookup])
        return attrs

    def optgroups(self, name, value, attrs=None):
        field = self.choices.field
        selected = {str(v) for v in value if str(v) not in field.empty_values}
        options = []
        if not self.allow_multiple_selected and field.empty_label is not None:
            options.append(self.create_option(name, "", field.empty_label, not selected, 0))
        to_field = field.to_field_name or "pk"
        chosen = []
        if selected:
            try:
                chosen = list(field.queryset.filter(**{f"{to_field}__in": selected}))
            except ValueError, TypeError:
                chosen = []  # a submitted value that is not even a key: the field's error says so
        for obj in chosen:
            option_value = field.prepare_value(obj)
            options.append(
                self.create_option(
                    name, option_value, field.label_from_instance(obj), True, len(options)
                )
            )
        return [(None, options, 0)]


class RemoteSelectMultiple(RemoteSelect, forms.SelectMultiple):
    """Multiple choice from a lookup (ModelMultipleChoiceField)."""

    allow_multiple_selected = True
