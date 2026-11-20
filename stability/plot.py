"""The drawing of a shelf-life evaluation for the ``shelf_life_chart`` component
(templates/includes/shelf_life_chart.html): coordinates in the SVG's own units, worked out in
``Decimal``, and the words of every mark. Presentation only: the results, the lines and the
estimate come from ``stability.shelf_life``.

Time on stability runs along the horizontal axis in months, from time zero to the later of the
data's end and the estimate. Each study's results have their own marker shape, named in the key,
so no colour is needed to tell the batches apart; a result outside its acceptance criterion is
filled in the danger tone. The mean line of each fit is solid, the confidence limit compared with
the criterion is dashed, the criterion is drawn as in a trend chart, and two upright lines mark
where the data end and the estimate.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from catalog.units import plain
from trending.plot import nice_step

from . import regression

WIDTH, HEIGHT = Decimal(960), Decimal(360)
LEFT, RIGHT, TOP, BOTTOM = Decimal(72), Decimal(828), Decimal(16), Decimal(310)
LABEL_GAP = Decimal(13)
SAMPLES = 48  # segments of each confidence limit curve
SHAPES = ("circle", "square", "triangle", "diamond", "down")
SHAPE_NAMES = {
    "circle": "circle",
    "square": "square",
    "triangle": "triangle",
    "diamond": "diamond",
    "down": "downward triangle",
}


def _c(value):
    return f"{value.quantize(Decimal('0.1')):f}"


def shape_path(shape, cx, cy, r=Decimal(5)):
    """The outline of a marker of ``shape`` centred on (cx, cy)."""
    match shape:
        case "square":
            return f"M{_c(cx - r)},{_c(cy - r)} H{_c(cx + r)} V{_c(cy + r)} H{_c(cx - r)} Z"
        case "triangle":
            return (
                f"M{_c(cx)},{_c(cy - r - 1)} L{_c(cx + r + 1)},{_c(cy + r)} "
                f"L{_c(cx - r - 1)},{_c(cy + r)} Z"
            )
        case "diamond":
            r += 1
            return (
                f"M{_c(cx)},{_c(cy - r)} L{_c(cx + r)},{_c(cy)} L{_c(cx)},{_c(cy + r)} "
                f"L{_c(cx - r)},{_c(cy)} Z"
            )
        case "down":
            return (
                f"M{_c(cx - r - 1)},{_c(cy - r)} L{_c(cx + r + 1)},{_c(cy - r)} "
                f"L{_c(cx)},{_c(cy + r + 1)} Z"
            )
    # A circle as a path, so every marker is drawn the same way.
    return (
        f"M{_c(cx - r)},{_c(cy)} a{_c(r)},{_c(r)} 0 1,0 {_c(2 * r)},0 "
        f"a{_c(r)},{_c(r)} 0 1,0 {_c(-2 * r)},0 Z"
    )


def legend_path(shape):
    return shape_path(shape, Decimal(8), Decimal(8), Decimal(4))


def _spread(labels):
    labels.sort(key=lambda label: label["y"])
    for before, after in zip(labels, labels[1:], strict=False):
        if after["y"] - before["y"] < LABEL_GAP:
            after["y"] = before["y"] + LABEL_GAP
    for label in labels:
        label["label_y"] = _c(label["y"] + 4)
    return labels


def _extent(result):
    """The months the drawing spans: a little past the later of the data's end and the
    estimate, or half as far again as the data when the limit never meets the criterion."""
    covered = max((point.months for point in result.points), default=Decimal(0))
    end = covered
    estimate = result.estimate.months if result.estimate else None
    if estimate is not None:
        end = max(end, estimate) * Decimal("1.05")
    elif result.analysis is not None:
        end = covered * Decimal("1.5")
    end = min(max(end, Decimal("0.5")), Decimal(regression.HORIZON))
    step = nice_step(end, 6)
    return (end / step).to_integral_value(ROUND_CEILING) * step, step


LABEL_ROOM = Decimal(150)  # the width a line's label needs beside it


def _place(marks):
    """Where each upright line's label goes: on the side with room, and on a second row when
    the two labels would meet."""
    for mark in marks:
        x = mark["at"]
        if mark["kind"] == "covered" and x - LEFT >= LABEL_ROOM:
            mark.update(anchor="end", dx="-4")
        elif mark["kind"] == "estimate" and RIGHT - x < LABEL_ROOM:
            mark.update(anchor="end", dx="-4")
        else:
            mark.update(anchor="start", dx="4")
        mark["label_y"] = _c(TOP + 10)
    if len(marks) == 2:
        first, second = marks
        reach = [
            (m["at"] - LABEL_ROOM, m["at"])
            if m["anchor"] == "end"
            else (m["at"], m["at"] + LABEL_ROOM)
            for m in marks
        ]
        if reach[0][0] < reach[1][1] and reach[1][0] < reach[0][1]:
            second["label_y"] = _c(TOP + 10 + LABEL_GAP)
    for mark in marks:
        mark["x"] = _c(mark.pop("at"))
    return marks


def geometry(evaluation, result, *, caption=""):
    """The drawing of ``result`` (``shelf_life.Result``) of ``evaluation``, or None."""
    points = result.points
    if not points:
        return None
    unit = evaluation.unit
    x_end, x_step = _extent(result)
    analysis, estimate = result.analysis, result.estimate
    pairs = regression.sides(evaluation.direction, evaluation.lower_limit, evaluation.upper_limit)
    fitted = result.fitted
    fits = list(analysis.fits) if analysis else []
    samples = [x_end * k / SAMPLES for k in range(SAMPLES + 1)]
    curves = []
    for fit in fits:
        values = [regression.limits(fit, estimate.t, x) for x in samples]
        for side, _ in pairs:
            curves.append([value[0 if side == "lower" else 1] for value in values])
    means = [(fit.mean(0), fit.mean(x_end)) for fit in fits]
    values = [point.value for point in points]
    values += [limit for _, limit in pairs]
    for curve in curves:
        values += curve
    for start, end in means:
        values += [start, end]
    low, high = min(values), max(values)
    pad = (high - low) * Decimal("0.06") if high > low else abs(low) / 10 or Decimal(1)
    low, high = low - pad, high + pad
    step = nice_step(high - low)
    low = (low / step).to_integral_value(ROUND_FLOOR) * step
    high = (high / step).to_integral_value(ROUND_CEILING) * step
    span = high - low

    def y(value):
        return BOTTOM - (value - low) / span * (BOTTOM - TOP)

    def x(months):
        return LEFT + months / x_end * (RIGHT - LEFT)

    shape_of = {
        batch.study.pk: SHAPES[number % len(SHAPES)] for number, batch in enumerate(result.batches)
    }
    markers = []
    for point in points:
        state = "oos" if not point.conforms else "result"
        cx, cy = x(point.months), y(point.value)
        title = (
            f"{point.study.identifier}, lot {point.study.lot.number}: {point.text} {unit} at "
            f"{point.pull.timepoint.label} ({plain(regression.round_half_up(point.months, 1))} "
            "months)"
        )
        if not point.conforms:
            title += ", outside the acceptance criterion"
        markers.append(
            {"d": shape_path(shape_of[point.study.pk], cx, cy), "state": state, "title": title}
        )
    lines, labels = [], []
    for (start, end), fit in zip(means, fits, strict=True):
        lines.append(
            {
                "kind": "mean",
                "x1": _c(x(Decimal(0))),
                "y1": _c(y(start)),
                "x2": _c(x(x_end)),
                "y2": _c(y(end)),
                "title": f"Mean line: {plain(regression.round_half_up(fit.intercept, 4))} "
                f"{'+' if fit.slope >= 0 else '−'} "
                f"{plain(regression.round_half_up(abs(fit.slope), 5))} × months",
            }
        )
    paths = [
        {
            "kind": "confidence",
            "d": " ".join(
                f"{'M' if k == 0 else 'L'}{_c(x(samples[k]))},{_c(y(value))}"
                for k, value in enumerate(curve)
            ),
        }
        for curve in curves
    ]
    for side, limit in pairs:
        name = "Lower limit" if side == "lower" else "Upper limit"
        lines.append(
            {
                "kind": "criterion",
                "x1": _c(LEFT),
                "y1": _c(y(limit)),
                "x2": _c(RIGHT),
                "y2": _c(y(limit)),
                "title": f"{name} {plain(limit)} {unit}",
            }
        )
        labels.append({"kind": "criterion", "y": y(limit), "text": f"{name} {plain(limit)}"})
    marks = []
    covered = result.covered_months
    if covered is not None:
        marks.append(
            {
                "kind": "covered",
                "at": x(covered),
                "text": f"Data to {plain(regression.round_half_up(covered, 1))} months",
            }
        )
    if result.estimate_months is not None and estimate.months <= x_end:
        marks.append(
            {
                "kind": "estimate",
                "at": x(estimate.months),
                "text": f"Estimate {plain(result.estimate_months)} months",
            }
        )
    y_ticks = []
    value = low
    while value <= high:
        y_ticks.append({"y": _c(y(value)), "label": plain(value), "label_y": _c(y(value) + 4)})
        value += step
    x_ticks = []
    months = Decimal(0)
    while months <= x_end:
        x_ticks.append({"x": _c(x(months)), "label": plain(months)})
        months += x_step
    key = [
        {
            "label": f"{batch.study.identifier} · lot {batch.study.lot.number}"
            + ("" if batch.fitted else " (not fitted)"),
            "d": legend_path(shape_of[batch.study.pk]),
        }
        for batch in result.batches
        if batch.points
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
        "markers": markers,
        "lines": lines,
        "paths": paths,
        "marks": _place(marks),
        "labels": _spread(labels),
        "y_ticks": y_ticks,
        "x_ticks": x_ticks,
        "key": key,
        "has_oos": any(marker["state"] == "oos" for marker in markers),
        "has_fit": bool(fits),
        "confidence": "Two-sided 95 % confidence limits"
        if evaluation.direction == "either"
        else "One-sided 95 % confidence limit",
        "unit": unit,
        "title": f"{evaluation.name} ({unit}) at {evaluation.condition} over months on "
        f"stability, {len(points)} results of {len([b for b in result.batches if b.points])} "
        "studies",
        "caption": caption,
        "fitted": len(fitted),
    }
