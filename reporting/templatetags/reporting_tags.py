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
