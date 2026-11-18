from datetime import UTC, datetime

from django import template

register = template.Library()


@register.filter
def stamp(value):
    """Frozen ISO timestamp (`2026-11-10T14:03:22Z`) -> `2026-11-10 14:03:22 UTC`."""
    if not value:
        return "—"
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is not None:
        moment = moment.astimezone(UTC)
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


@register.filter
def section_items(value):
    """Frozen specification/method sections as (label, text) pairs, whatever their shape."""
    if isinstance(value, dict):
        return [(str(k), str(v)) for k, v in sorted(value.items())]
    if isinstance(value, list):
        return [("", str(item)) for item in value]
    return [("", str(value))]


@register.simple_tag
def certificate_scope(snapshot, scope=""):
    """What a certificate for one scope of the lot reports (`conformity.scope_view`), from the
    snapshot or the evidence alone; None for a certificate of all of the lot's requirements."""
    from reporting.conformity import scope_view

    return scope_view(snapshot, scope)


@register.simple_tag
def certificate_headings(pdf=False):
    """Heading levels of the certificate: under the page's own h1 on screen, and from h1 in the
    issued PDF, whose tagged structure must start at h1 and skip no level (PDF/UA-1, 7.4.2)."""
    return {"title": 1, "section": 2} if pdf else {"title": 2, "section": 3}


@register.filter
def outcome_label(outcome):
    """The words of a conformity outcome (`reporting.conformity`)."""
    from reporting.conformity import OUTCOME_LABELS

    return OUTCOME_LABELS.get(outcome, outcome)


@register.filter
def outcome_tone(outcome):
    from reporting.conformity import OUTCOME_TONES

    return OUTCOME_TONES.get(outcome, "neutral")


@register.simple_tag
def decision_rule():
    """How the certificate judges conformity, in words."""
    from reporting.conformity import DECISION_RULE

    return DECISION_RULE


@register.filter
def distinct_methods(methods):
    """The methods a certificate names, each version once: the evidence lists the method of
    every required test, so a method used by several tests appears once per test there."""
    if not isinstance(methods, list):
        return methods
    seen, found = set(), []
    for method in methods:
        key = (method.get("code"), method.get("version")) if isinstance(method, dict) else method
        key = repr(key)
        if key not in seen:
            seen.add(key)
            found.append(method)
    return found
