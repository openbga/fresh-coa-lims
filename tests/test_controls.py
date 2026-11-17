"""Form controls never show the browser's default UI (docs/ui-standards.md, Lists and forms).

Each control is one widget template in templates/django/forms/widgets/ plus static/js/controls.js.
A page gets it through a Django form field, never by writing the native element itself.
"""

import re
from pathlib import Path

from django import forms
from django.conf import settings

from core.forms import PINForm, SignForm

ROOT = Path(settings.BASE_DIR)
WIDGETS = ROOT / "templates/django/forms/widgets"
SKIP_DIRS = {".venv", "node_modules", "staticfiles", ".local", ".git", "build"}

NATIVE = re.compile(
    r"<select\b|<datalist\b"
    r"|<input\b[^>]*\btype=[\"']?(?:date|datetime-local|time|month|week|number|file)\b",
    re.IGNORECASE,
)


def project_templates():
    """Django templates only: files under a templates/ directory (never runtime output)."""
    for path in ROOT.rglob("templates/**/*.html"):
        parts = path.relative_to(ROOT).parts
        if SKIP_DIRS.intersection(parts) or path.is_relative_to(WIDGETS):
            continue
        yield path


def test_no_native_control_outside_its_widget():
    """A raw <select>, <datalist> or date/number/file <input> in a page template bypasses the
    shared component: render a form field instead ({{ form.x }})."""
    problems = []
    for path in project_templates():
        text = path.read_text()
        for match in NATIVE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"{path.relative_to(ROOT)}:{line} {match.group()}")
    assert not problems, "Native controls outside their widget:\n" + "\n".join(problems)


class Controls(forms.Form):
    count = forms.IntegerField(min_value=1)
    signed = forms.IntegerField()
    amount = forms.DecimalField(min_value=0, decimal_places=2)
    result = forms.DecimalField(max_digits=20, decimal_places=8)
    quantity = forms.DecimalField(
        widget=forms.NumberInput(attrs={"inputmode": "decimal", "step": "any"})
    )
    day = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "max": "2099-12-31"}))
    moment = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
    )
    document = forms.FileField(
        widget=forms.FileInput(attrs={"accept": ".csv,application/pdf", "data-vr-max-bytes": 9})
    )
    optional_document = forms.FileField(required=False)
    assay = forms.DecimalField(
        help_text="As read.", widget=forms.NumberInput(attrs={"unit": "% w/w"})
    )
    kind = forms.ChoiceField(choices=[("a", "A"), ("b", "B")])
    flag = forms.BooleanField(required=False)


def test_number_is_text_with_exact_string_and_safe_keypad():
    form = Controls(initial={"amount": "0.0100"})
    amount = str(form["amount"])
    assert 'type="text"' in amount and "vr-number" in amount
    assert 'value="0.0100"' in amount  # the typed string, not a float
    assert 'inputmode="decimal"' in amount
    assert not re.search(r"\b(min|max|step)=", amount)  # the server validates
    assert 'inputmode="numeric"' in str(form["count"])
    # No lower bound: negatives are possible, and touch keypads for these modes lack a minus.
    assert "inputmode" not in str(form["signed"]) and "inputmode" not in str(form["result"])
    assert str(form["quantity"]).count("inputmode") == 1  # an explicit inputmode wins


def test_submitted_decimal_is_echoed_exactly_as_typed():
    form = Controls(data={"result": "1.50000000", "amount": "x"})
    assert 'value="1.50000000"' in str(form["result"])
    assert 'value="x"' in str(form["amount"])  # an invalid entry is kept for correction


def test_number_unit_is_one_input_group_read_with_the_field():
    assay = " ".join(str(Controls()["assay"]).split())
    assert assay.startswith('<div class="input-group vr-unit-group"><input type="text"')
    assert 'aria-describedby="id_assay_helptext id_assay_unit"' in assay
    assert '<span class="input-group-text" id="id_assay_unit">% w/w</span></div>' in assay
    assert ' unit="' not in assay


def test_dates_keep_their_native_input_and_server_format():
    form = Controls(initial={"moment": "2026-11-13T09:30"})
    day = str(form["day"])
    moment = str(form["moment"])
    assert 'type="date"' in day and 'data-vr-date="date"' in day and 'max="2099-12-31"' in day
    assert 'type="datetime-local"' in moment and 'data-vr-date="datetime"' in moment
    assert 'value="2026-11-13T09:30"' in moment
    assert f'data-vr-time-zone="{settings.TIME_ZONE}"' in moment


def test_file_inputs_render_the_drop_zone():
    form = Controls()
    document = str(form["document"])
    assert "data-vr-file" in document and 'class="vr-drop" for="id_document"' in document
    assert 'accept=".csv,application/pdf"' in document and "data-vr-file-name" in document
    assert 'data-vr-max-bytes="9"' in document  # the browser's size check stays on the input
    assert "data-vr-file" in str(form["optional_document"])  # ClearableFileInput too


def test_raw_data_upload_keeps_its_size_check():
    from analytical.rawdata import RawFileForm

    upload = str(RawFileForm()["file"])
    assert "data-vr-file" in upload and "data-vr-max-bytes=" in upload


def test_widgets_decide_their_own_class():
    form = Controls()
    assert 'class="form-select"' in str(form["kind"])
    assert 'class="form-check-input"' in str(form["flag"])
    assert 'class="form-control" ' not in str(form["kind"])


def test_pin_fields_hint_digits_and_are_never_autofilled_or_echoed():
    for form, name in ((SignForm(data={"pin": "12345678"}), "pin"), (PINForm(), "pin")):
        html = str(form[name])
        assert 'type="password"' in html
        assert 'inputmode="numeric"' in html and 'autocomplete="off"' in html
        assert "12345678" not in html


def test_vendored_libraries_and_inline_calendar():
    for path in (
        "static/vendor/tom-select/tom-select.complete.min.js",
        "static/vendor/tom-select/LICENSE",
        "static/vendor/vanilla-calendar-pro-3.4.0/index.js",
        "static/vendor/vanilla-calendar-pro-3.4.0/LICENSE",
    ):
        assert (ROOT / path).exists(), path
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    assert "Tom Select 2.7.0" in notices and "Vanilla Calendar Pro 3.4.0" in notices
    script = (ROOT / "static/js/controls.js").read_text()
    # Inline mode only: the library's input popup appends to <body> and breaks modal focus.
    assert "inputMode" not in script
    assert "firstWeekday: 0" in script  # weeks start on Sunday


def test_preferences_never_live_in_the_browser():
    for name in ("preferences.js", "sidebar.js", "controls.js"):
        script = (ROOT / "static/js" / name).read_text()
        assert "localStorage.setItem" not in script, name
