"""The geometry of a trend chart for the ``trend_chart`` component (templates/includes/
trend_chart.html): coordinates in the SVG's own units, worked out in ``Decimal`` like everything
else, and the words of every mark. Presentation only: the values, limits and flags come from
``series``.

Results are plotted one after another in the order their reviews were signed, evenly spaced.
The center line and the limits are drawn as steps, each version over the results it judged; the
specification limits likewise, from each result's frozen requirement. The vertical range covers
the results and the chart's limits; a specification limit far outside them is named instead of
drawn, so it does not flatten the results.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from django.utils import timezone

from catalog.units import plain

from .rules import describe

WIDTH, HEIGHT = Decimal(960), Decimal(340)
LEFT, RIGHT, TOP, BOTTOM = Decimal(72), Decimal(828), Decimal(16), Decimal(300)
LABEL_GAP = Decimal(13)  # the least vertical distance between two line labels
SPEC_REACH = Decimal("0.5")  # a spec limit further than this share of the span is named only
X_TICKS = 6
NICE = (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5), Decimal(10))


def _c(value):
    """A coordinate as the SVG writes it."""
    return f"{value.quantize(Decimal('0.1')):f}"


def nice_step(span, ticks=5):
    """A round step (1, 2, 2.5 or 5 times a power of ten) giving about ``ticks`` intervals."""
    raw = span / ticks
    power = Decimal(1).scaleb(raw.adjusted())
    for factor in NICE:
        if raw <= factor * power:
            return factor * power
    return 10 * power


def _range(values):
    low, high = min(values), max(values)
    if low == high:
        pad = abs(low) / 10 or Decimal(1)
    else:
        pad = (high - low) * Decimal("0.08")
    return low - pad, high + pad


def _segments(points, key):
    """Consecutive runs of ``points`` with the same ``key(point)``: (first, last, key)."""
    runs = []
    for point in points:
        value = key(point)
        if runs and runs[-1][2] == value:
            runs[-1][1] = point
        else:
            runs.append([point, point, value])
    return [tuple(run) for run in runs]


def _marker(point):
    if not point.conforms:
        return "oos"
    if point.open_alert:
        return "alert"
    if point.raised:
        return "evaluated"
    return "result"


def _shape(kind, cx, cy):
    """The outline of a flagged marker: a diamond for an alert, a square for a result out of
    specification. A plain result is a circle, drawn by the template."""
    if kind in ("alert", "evaluated"):
        r = Decimal(6)
        return (
            f"M{_c(cx)},{_c(cy - r)} L{_c(cx + r)},{_c(cy)} L{_c(cx)},{_c(cy + r)} "
            f"L{_c(cx - r)},{_c(cy)} Z"
        )
    if kind == "oos":
        r = Decimal(5)
        return f"M{_c(cx - r)},{_c(cy - r)} H{_c(cx + r)} V{_c(cy + r)} H{_c(cx - r)} Z"
    return ""


def _point_title(point, unit):
    test = point.test
    when = timezone.localtime(point.reviewed_at).strftime("%Y-%m-%d")
    parts = [
        f"{test.label}, lot {test.lot.number}",
        f"{point.text} {unit}",
        f"reviewed {when}",
    ]
    if not point.conforms:
        parts.append("out of specification")
    if point.raised:
        limits = point.limits
        rules = "; ".join(
            describe(rule, run_length=limits.run_length, trend_length=limits.trend_length)
            for rule in point.rules
        )
        state = "evaluated" if point.covered else "not evaluated"
        parts.append(f"alert ({state}): {rules}")
    return " · ".join(parts)


def _spread(labels):
    """Move line labels apart vertically so none overlaps another."""
    labels.sort(key=lambda label: label["y"])
    for before, after in zip(labels, labels[1:], strict=False):
        if after["y"] - before["y"] < LABEL_GAP:
            after["y"] = before["y"] + LABEL_GAP
    for label in labels:
        label["label_y"] = _c(label["y"] + 4)
    return labels


def geometry(chart, points, *, caption=""):
    """The drawing of ``points`` (``series.Point``, oldest first) of ``chart``."""
    if not points:
        return None
    unit = chart.unit
    values = [point.value for point in points]
    for point in points:
        if point.limits is not None:
            values += [
                v
                for v in (point.limits.lower, point.limits.upper, point.limits.center)
                if v is not None
            ]
    low, high = min(values), max(values)
    reach = (high - low) * SPEC_REACH if high > low else abs(high) or Decimal(1)
    named = []
    for point in points:
        for limit in point.spec_limits:
            if limit is None:
                continue
            if low - reach <= limit <= high + reach:
                values.append(limit)
            elif plain(limit) not in named:
                named.append(plain(limit))
    bottom_value, top_value = _range(values)
    step = nice_step(top_value - bottom_value)
    bottom_value = (bottom_value / step).to_integral_value(ROUND_FLOOR) * step
    top_value = (top_value / step).to_integral_value(ROUND_CEILING) * step
    span = top_value - bottom_value

    def y(value):
        return BOTTOM - (value - bottom_value) / span * (BOTTOM - TOP)

    pitch = (RIGHT - LEFT) / len(points)

    def x(index):
        return LEFT + pitch * index + pitch / 2

    position = {id(point): number for number, point in enumerate(points)}

    def ends(first, last):
        return x(position[id(first)]) - pitch / 2, x(position[id(last)]) + pitch / 2

    lines, labels = [], []

    def line(kind, first, last, value, text, label):
        start, end = ends(first, last)
        lines.append(
            {"kind": kind, "x1": _c(start), "x2": _c(end), "y": _c(y(value)), "title": text}
        )
        if label:
            labels.append({"kind": kind, "y": y(value), "text": text})

    limited = [run for run in _segments(points, lambda p: p.limits) if run[2] is not None]
    for number, (first, last, limits) in enumerate(limited):
        latest = number == len(limited) - 1
        version = f"v{limits.version}"
        if limits.center is not None:
            line("center", first, last, limits.center, f"Center {plain(limits.center)}", latest)
        for name, value in (("Upper", limits.upper), ("Lower", limits.lower)):
            if value is not None:
                line("limit", first, last, value, f"{name} {plain(value)} ({version})", latest)
    specs = _segments(points, lambda p: p.spec_limits)
    for number, (first, last, (lower, upper)) in enumerate(specs):
        latest = number == len(specs) - 1
        for name, value in (("Upper spec", upper), ("Lower spec", lower)):
            if value is not None and bottom_value <= value <= top_value:
                line("spec", first, last, value, f"{name} {plain(value)}", latest)

    ticks = []
    value = bottom_value
    while value <= top_value:
        ticks.append({"y": _c(y(value)), "label": plain(value), "label_y": _c(y(value) + 4)})
        value += step
    shown = sorted({round(i * (len(points) - 1) / (X_TICKS - 1)) for i in range(X_TICKS)})
    x_ticks = [
        {
            "x": _c(x(index)),
            "label": timezone.localtime(points[index].reviewed_at).strftime("%Y-%m-%d"),
        }
        for index in shown
    ]
    markers = [
        {
            "kind": _marker(point),
            "x": _c(x(number)),
            "y": _c(y(point.value)),
            "d": _shape(_marker(point), x(number), y(point.value)),
            "title": _point_title(point, unit),
        }
        for number, point in enumerate(points)
    ]
    return {
        "view_box": f"0 0 {WIDTH} {HEIGHT}",
        "left": _c(LEFT),
        "right": _c(RIGHT),
        "top": _c(TOP),
        "bottom": _c(BOTTOM),
        "label_x": _c(RIGHT + 8),
        "tick_x": _c(LEFT - 8),
        "axis_label_y": _c(BOTTOM + 22),
        "path": " ".join(
            f"{'M' if number == 0 else 'L'}{marker['x']},{marker['y']}"
            for number, marker in enumerate(markers)
        ),
        "markers": markers,
        "lines": lines,
        "labels": _spread(labels),
        "y_ticks": ticks,
        "x_ticks": x_ticks,
        "unit": unit,
        "title": f"{chart.name} ({unit}) of {chart.material.code}, {len(points)} results",
        "caption": caption,
        "named_specs": named,
        "kinds": sorted({marker["kind"] for marker in markers} | {line["kind"] for line in lines}),
    }
