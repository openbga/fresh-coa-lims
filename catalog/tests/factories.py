"""Synthetic fixtures shared by catalog and sampling tests. All names and values are fictional."""

import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.utils import timezone

from catalog import services
from core.models import RuleSet
from core.services import set_pin

PIN = "48213957"
PASSWORD = "synthetic-pass-6182-A"


def person(username, *roles):
    user = get_user_model().objects.create_user(
        username=username, password=PASSWORD, first_name="Test", last_name=username.title()
    )
    for role in roles:
        user.groups.add(Group.objects.get_or_create(name=role)[0])
    set_pin(actor=user, pin=PIN, password=PASSWORD)
    return user


def window(start_days=-1, end_days=365):
    now = timezone.now()
    return now + timedelta(days=start_days), now + timedelta(days=end_days)


def approve(revision, actor, **overrides):
    revision.refresh_from_db()
    kwargs = {
        "actor": actor,
        "pin": PIN,
        "revision": revision,
        "expected_revision": revision.revision,
        "reason": "Independent synthetic review",
    }
    kwargs.update(overrides)
    return services.approve_revision(**kwargs)


def material(actor, code="syn-api-001", kind="raw_material"):
    return services.create_material(
        actor=actor, code=code, name=f"Synthetic {code}", kind=kind, reason="Synthetic master data"
    )


def method_revision(actor, code="hplc-assay", start_days=-1, end_days=365, method=None):
    start, end = window(start_days, end_days)
    fields = {
        "technique": "HPLC-UV",
        "document_ref": f"SOP-SYN-{code} rev 1",
        "suitability_kind": "validation",
        "suitability_ref": f"VAL-SYN-{code}",
        "effective_from": start,
        "effective_until": end,
        "reason": "Synthetic method",
    }
    if method is not None:
        return services.new_method_revision(actor=actor, method=method, **fields)
    return services.create_method(actor=actor, code=code, title=f"Synthetic {code}", **fields)[1]


def specification(actor, mat, code="spec-api", stage="incoming", scope="general", days=(-1, 365)):
    start, end = window(*days)
    return services.create_specification(
        actor=actor,
        code=code,
        title=f"Synthetic {code}",
        material=mat,
        stage=stage,
        scope=scope,
        basis="Synthetic limits for testing only",
        effective_from=start,
        effective_until=end,
        reason="Synthetic specification",
    )


def numeric_line(actor, revision, method, code="assay", low="98.0", high="102.0", **extra):
    fields = {
        "code": code,
        "name": code.title(),
        "method": method,
        "result_type": "numeric",
        "unit": "%",
        "lower_limit": Decimal(low) if low is not None else None,
        "upper_limit": Decimal(high) if high is not None else None,
    }
    fields.update(extra)
    return services.add_test_line(actor=actor, revision=revision, reason="Add test", **fields)


def qualitative_line(actor, revision, method, code="identity", expected="Conforms"):
    return services.add_test_line(
        actor=actor,
        revision=revision,
        reason="Add test",
        code=code,
        name=code.title(),
        method=method,
        result_type="qualitative",
        expected_text=expected,
    )


def approved_rules(author, required=("identity",)):
    start, end = window()
    return RuleSet.objects.create(
        code=f"syn-{'-'.join(required)}",
        segment="pharma",
        author=author,
        status="approved",
        effective_from=start,
        effective_until=end,
        policy={
            "required_tests": list(required),
            "review_meaning": "reviewed",
            "disposition_meaning": "approved",
        },
    )


def approved_specification(author, approver, mat, stage="incoming"):
    """An approved specification with an identity and an assay test, methods approved."""
    identity = method_revision(author, code="ftir-identity")
    assay = method_revision(author, code="hplc-assay")
    approve(identity, approver)
    approve(assay, approver)
    spec, revision = specification(author, mat, code=f"spec-{mat.code}-{stage}", stage=stage)
    qualitative_line(author, revision, identity.method, code="identity")
    numeric_line(author, revision, assay.method, code="assay", reporting_decimals=1)
    return approve(revision, approver)


def commit_first_on_save(monkeypatch, model, competitor):
    """Emulate a concurrent request: just before this request's first insert of ``model``,
    ``competitor()`` commits a conflicting row on its own connection. Every uniqueness check
    this request made has passed by then, so only the database constraint can catch it."""
    real_save = model.save
    raced = []

    def save(self, *args, **kwargs):
        if not raced and self._state.adding:
            raced.append(True)
            errors = []

            def other_request():
                try:
                    competitor()
                except Exception as exc:  # surfaced in the test below
                    errors.append(exc)
                finally:
                    connection.close()

            thread = threading.Thread(target=other_request)
            thread.start()
            thread.join(timeout=30)
            assert not thread.is_alive() and not errors, errors
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(model, "save", save)
