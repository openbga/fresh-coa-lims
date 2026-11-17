"""Server-side list paging shared by every list page (docs/ui-standards.md, Lists and forms).

paginate() reads ?page= and ?per_page= (one of PAGE_SIZES); PageSizeForm is the rows-per-page
field of the shared pagination component (includes/pagination.html), rendered through the widget
templates like every other control.
"""

from django import forms
from django.core.paginator import Paginator

PAGE_SIZES = (25, 50, 100)


class PageSizeForm(forms.Form):
    per_page = forms.TypedChoiceField(
        label="Rows per page",
        choices=[(size, str(size)) for size in PAGE_SIZES],
        coerce=int,
    )


def page_size(request, default=PAGE_SIZES[0]):
    """The requested rows per page when it is one of PAGE_SIZES, else the default."""
    try:
        size = int(request.GET.get("per_page", default))
    except TypeError, ValueError:
        return default
    return size if size in PAGE_SIZES else default


def paginate(request, queryset, default=PAGE_SIZES[0]):
    """The requested page of queryset, at the requested rows per page."""
    return Paginator(queryset, page_size(request, default)).get_page(request.GET.get("page"))
