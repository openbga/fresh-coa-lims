"""Every date and date-time field uses the shared date control (docs/ui-standards.md, "Lists and
forms"): templates/django/forms/widgets/date.html, enhanced by static/js/controls.js with the
calendar popover. A date-time is local time to the minute (core.forms.LocalDateTimeInput), so no
field shows seconds or a browser's bare text box."""

import importlib
import pkgutil

from django import forms
from django.apps import apps
from django.conf import settings


def project_forms():
    root = str(settings.BASE_DIR)
    local = set()
    for config in apps.get_app_configs():
        if not config.path.startswith(root) or ".venv" in config.path:
            continue
        local.add(config.name.split(".")[0])
        for module in pkgutil.walk_packages([config.path], config.name + "."):
            if "form" in module.name.rsplit(".", 1)[-1] or module.name.endswith("views"):
                importlib.import_module(module.name)
    seen, stack = set(), list(forms.BaseForm.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack += cls.__subclasses__()
        if cls.__module__.split(".")[0] in local:
            yield cls


def test_date_and_time_fields_use_the_shared_control():
    checked, offenders = 0, []
    for cls in project_forms():
        for name, field in getattr(cls, "base_fields", {}).items():
            widget = field.widget
            where = f"{cls.__module__}.{cls.__name__}.{name}: {type(widget).__name__}"
            if isinstance(widget, forms.HiddenInput):
                continue
            if isinstance(field, forms.DateTimeField):
                checked += 1
                kind = widget.attrs.get("type", getattr(widget, "input_type", ""))
                if kind != "datetime-local" or not str(widget.format or "").startswith("%Y-%m-%dT"):
                    offenders.append(where)
            elif isinstance(field, forms.DateField):
                checked += 1
                if widget.attrs.get("type", getattr(widget, "input_type", "")) != "date":
                    offenders.append(where)
    assert checked > 5, "the scan found too few date fields"
    assert not offenders, "Use core.forms.LocalDateTimeInput or a date input:\n" + "\n".join(
        offenders
    )
