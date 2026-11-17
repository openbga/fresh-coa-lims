"""Server-side list paging shared by every list page (docs/ui-standards.md, Lists and forms).

paginate() reads ?page= and ?per_page= (one of PAGE_SIZES); PageSizeForm is the rows-per-page
field of the shared pagination component (includes/pagination.html), rendered through the widget
templates like every other control.

Column declares one column of a list once (in the view): its stable key, its heading, its sort
values and its priority. {% grid_table %} renders the header row from it with the data-vr-grid /
data-vr-col hooks static/js/grid.js needs, and {% list_results grid=... %} adds the Columns
button, so every list saves its column layout per user (core/preferences.py).
"""

from dataclasses import dataclass

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


@dataclass(frozen=True)
class Column:
    """One list column: key (stable data-vr-col id, never renamed), label (heading), optional
    asc/desc sort values (the view validates them), first ("desc" to sort newest first),
    priority ("low", then "medium": hidden by default when the table would not fit), locked
    (always shown: the row identifier), label_hidden (visually hidden heading, e.g. an Actions
    column), css (th classes such as "text-end")."""

    key: str
    label: str
    asc: str = ""
    desc: str = ""
    first: str = ""
    priority: str = ""
    locked: bool = False
    label_hidden: bool = False
    css: str = ""
