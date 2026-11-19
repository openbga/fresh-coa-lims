"""Qualifications for authorizing the decisions a rule set reserves (OQ-004).

A rule set version may reserve two kinds of decision on the lots under it for people holding an
approved, current qualification for an activity it names (policy key ``authorization``):

- ``release``: the release of a lot, and the conclusion of its reassessment that keeps the
  material in use until a later retest date;
- ``certificate``: the issue and the amendment of a certificate of analysis for it.

A lot is under its own rule set version and the additional ones frozen with its requirements
(``sampling.services.applied_rules``). Every one of them that reserves a decision asks for its
activity, so a signer may need more than one qualification. Approved policies never change, so
what a lot asks for is fixed by the versions it is under.

The rejection and the cancellation of a lot, the withdrawal of a certificate and the conclusion
that ends the use of material are not reserved: none of them puts material into use or states
that it conforms, and a lot is never kept from them for want of a qualified signer.

``refusal`` is the read-only check shown before any PIN is asked for. ``authorize`` runs inside
the decision's signed transition, after the signer's account and the record signed are locked:
it locks the signer's qualification rows for each activity before reading them, so a revocation
signed meanwhile either waits for the decision or is seen by it, and returns what is frozen with
the decision (empty when nothing is reserved), or refuses.
"""

from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.services import AUTHORIZATION, AUTHORIZED_DECISIONS
from laboratory.models import Qualification

RELEASE, CERTIFICATE = "release", "certificate"
WORK = {RELEASE: Qualification.Work.RELEASE, CERTIFICATE: Qualification.Work.CERTIFY}


def _rules_of(lot):
    from sampling.services import applied_rules

    return applied_rules(lot)


def reserved(lot, decision, rules=None):
    """What the lot's rule set versions reserve for ``decision``: one entry per activity
    (compared without regard to case, as qualifications are), each with the versions that name
    it, in the order of the lot's rule sets."""
    found = {}
    for rule in _rules_of(lot) if rules is None else rules:
        policy = rule.policy if isinstance(rule.policy, dict) else {}
        named = policy.get(AUTHORIZATION)
        activity = named.get(decision) if isinstance(named, dict) else None
        if not isinstance(activity, str) or not activity.strip():
            continue
        activity = activity.strip()
        entry = found.setdefault(activity.lower(), {"activity": activity, "rule_sets": []})
        entry["rule_sets"].append({"id": rule.pk, "code": rule.code, "version": rule.version})
    return list(found.values())


def rule_sets_text(entry):
    names = [f"{item['code']} v{item['version']}" for item in entry["rule_sets"]]
    noun = "Rule set" if len(names) == 1 else "Rule sets"
    return f"{noun} {' and '.join(names)}"


def requirement_text(entry, decision):
    """How a reservation reads: who may sign the decision, and which rule sets ask for it."""
    return (
        f"{rule_sets_text(entry)} reserves {AUTHORIZED_DECISIONS[decision]} for people "
        f"qualified for “{entry['activity']}”."
    )


def _missing(entry, decision):
    return (
        f"{requirement_text(entry, decision)} You hold no approved, current qualification for it."
    )


def _finding(actor, entry, decision, lock):
    from laboratory.services import authority_finding

    return authority_finding(
        actor=actor, activity=entry["activity"], work=WORK[decision], lock=lock
    )


def refusal(actor, lot, decision, rules=None):
    """Why ``actor`` may not sign ``decision`` on the lot now, or "". Read-only and unlocked:
    ``authorize`` repeats it under the locks when signing."""
    return " ".join(
        _missing(entry, decision)
        for entry in reserved(lot, decision, rules)
        if not _finding(actor, entry, decision, lock=False).ok
    )


def authorize(actor, lot, decision, rules=None):
    """Inside the decision's transaction: lock and check the signer's qualifications for every
    activity reserved, and return the evidence frozen with the decision ([] when the lot's rule
    sets reserve nothing)."""
    evidence, reasons = [], []
    for entry in reserved(lot, decision, rules):
        finding = _finding(actor, entry, decision, lock=True)
        if finding.ok:
            evidence.append({**entry, "qualification": finding.evidence["qualification"]})
        else:
            reasons.append(_missing(entry, decision))
    if reasons:
        raise ValidationError(" ".join(reasons))
    return evidence


def relied_text(item, decision):
    return (
        f"QUAL-{item['qualification']}, for {AUTHORIZED_DECISIONS[decision]} in "
        f"“{item['activity']}” ({rule_sets_text(item)})"
    )


def notices(actor, lot, decision, rules=None):
    """What the signer of a reserved decision should see: the qualifications the signature
    relies on, which are recorded with it. Empty when nothing is reserved or one is missing
    (the refusal says so instead)."""
    entries = reserved(lot, decision, rules)
    found = [(entry, _finding(actor, entry, decision, lock=False)) for entry in entries]
    if not found or not all(finding.ok for _, finding in found):
        return []
    held = "; ".join(
        relied_text({**entry, "qualification": finding.evidence["qualification"]}, decision)
        for entry, finding in found
    )
    return [f"This signature relies on your qualification {held}, and records it."]


def describe(evidence, decision):
    """Frozen evidence as the pages show it: one line per qualification relied on, with its
    page and what it is for."""
    return [
        {
            "label": f"QUAL-{item['qualification']}",
            "href": reverse("laboratory:qualification_detail", args=[item["qualification"]]),
            "text": f"For {AUTHORIZED_DECISIONS[decision]} in “{item['activity']}” "
            f"({rule_sets_text(item)})",
        }
        for item in evidence or []
        if isinstance(item, dict) and isinstance(item.get("qualification"), int)
    ]


def relied_on(qualification):
    """The decisions signed in reliance on ``qualification``: released lots, reassessments
    concluded suitable and certificate versions, each as (kind, label, href)."""
    pk = qualification.pk
    held = [{"qualification": pk}]
    rows = []
    lot_model = apps.get_model("quality", "Lot")
    for lot in lot_model.objects.filter(
        disposition_evidence__contains={AUTHORIZATION: held}
    ).order_by("pk"):
        rows.append(("Release", lot.number, reverse("quality:lot_detail", args=[lot.pk])))
    reassessment_model = apps.get_model("quality", "Reassessment")
    for item in (
        reassessment_model.objects.filter(result_evidence__contains={AUTHORIZATION: held})
        .select_related("lot")
        .order_by("pk")
    ):
        rows.append(
            (
                "Reassessment concluded suitable",
                f"{item.label} · {item.lot.number}",
                reverse("quality:reassessment_detail", args=[item.pk]),
            )
        )
    if apps.is_installed("reporting"):
        version_model = apps.get_model("reporting", "ReportVersion")
        for version in (
            version_model.objects.filter(snapshot__contains={"report": {AUTHORIZATION: held}})
            .select_related("report")
            .defer("pdf", "data", "snapshot")
            .order_by("pk")
        ):
            rows.append(
                (
                    "Certificate issued" if version.kind == "issue" else "Certificate amended",
                    f"{version.report.number} version {version.number}",
                    reverse("reporting:version", args=[version.report_id, version.number]),
                )
            )
    return rows
