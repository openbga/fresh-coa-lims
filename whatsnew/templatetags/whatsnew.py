"""Shell hook for What's new: {% load whatsnew %}{% whatsnew_button %} in the top bar."""

from django import template

from whatsnew import catalogue

register = template.Library()


@register.inclusion_tag("whatsnew/button.html", takes_context=True)
def whatsnew_button(context):
    """The top-bar link to What's new, with the number of changes this user has not seen."""
    request = context.get("request")
    if request is None:
        return {"unread": 0, "current": False}
    match = request.resolver_match
    unread = catalogue.unread_count(request)
    return {
        "unread": unread,
        "badge": "99+" if unread > 99 else unread,
        "current": bool(match and match.view_name == "whatsnew:index"),
    }
