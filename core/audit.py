import json
from functools import cache

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.forms.models import model_to_dict

from .models import AuditEvent


def record_event(*, actor, action, obj, before=None, after=None, reason=""):
    if not connection.in_atomic_block:
        raise RuntimeError("Audit events must share the domain transaction.")
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=str(obj.pk),
        before=before or {},
        after=after or {},
        reason=reason,
    )


def snapshot(obj):
    """Serializable field snapshot; never call this on credentials/account models."""
    return json.loads(json.dumps(model_to_dict(obj), cls=DjangoJSONEncoder))


@cache
def _choices_by_field_name():
    """{field name: {stored code: label}} over every model field with choices, keeping only the
    codes whose label is the same wherever that field name is used."""
    from collections import defaultdict

    from django.apps import apps

    found = defaultdict(lambda: defaultdict(set))
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if getattr(field, "choices", None):
                for code, label in field.flatchoices:
                    found[field.name][str(code)].add(str(label))
    return {
        name: {code: next(iter(names)) for code, names in codes.items() if len(names) == 1}
        for name, codes in found.items()
    }


@cache
def choice_labels(object_type=""):
    """{key: {stored code: label}} for showing an audit snapshot in words: the choices of the
    event's own model (object_type "app_label.model") first, then any field of that name whose
    label for the code is unambiguous across models (nested snapshots, e.g. a lot's receipt)."""
    from django.apps import apps

    labels = dict(_choices_by_field_name())
    try:
        model = apps.get_model(object_type) if object_type else None
    except LookupError, ValueError:
        model = None
    if model is not None:
        for field in model._meta.get_fields():
            if getattr(field, "choices", None):
                labels[field.name] = {str(code): str(label) for code, label in field.flatchoices}
    return labels
