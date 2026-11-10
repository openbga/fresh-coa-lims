"""Shell hooks for the page documentation panel. See pagedocs/templates/pagedocs/*.html."""

from django import template
from django.urls import reverse
from django.utils.http import urlencode

register = template.Library()


def _context(context):
    request = context.get("request")
    path = request.path if request else "/"
    return {
        "request": request,
        "endpoint": reverse("pagedocs:doc"),
        "full_url": f"{reverse('pagedocs:doc')}?{urlencode({'path': path})}",
    }


@register.inclusion_tag("pagedocs/head.html")
def pagedocs_head():
    """Stylesheet and the synchronous pre-paint state script; place in <head>."""
    return {}


@register.inclusion_tag("pagedocs/button.html", takes_context=True)
def pagedocs_button(context):
    """Top-bar toggle; place last inside the top bar's right-hand group."""
    return _context(context)


@register.inclusion_tag("pagedocs/panel.html", takes_context=True)
def pagedocs_panel(context):
    """The complementary panel and its script; place after the shell, before </body>."""
    return _context(context)
