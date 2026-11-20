"""The drawing of a shelf-life evaluation (stability.plot), from frozen content replayed through
the statistics, so no database is needed."""

from decimal import Decimal
from types import SimpleNamespace

from stability import plot, regression, shelf_life


def content(days, series, *, lower="95", upper="105", direction="decreases"):
    """Frozen content of an evaluation with one study per entry of ``series``."""
    studies = [f"STB-{n}" for n in range(1, len(series) + 1)]
    results = [
        {
            "study": study,
            "lot": f"LOT-{study}",
            "pull": n * 10 + k,
            "condition": "Long-term",
            "timepoint": f"Day {d}",
            "interval_days": d,
            "test": n * 10 + k,
            "value": value,
            "reportable": value,
            "conforms": Decimal(value) >= Decimal(lower),
            "fitted": True,
        }
        for n, (study, values) in enumerate(zip(studies, series, strict=True))
        for k, (d, value) in enumerate(zip(days, values, strict=True))
    ]
    return {
        "protocol_code": "SYN",
        "container_closure": "Synthetic bottle",
        "condition": "Long-term",
        "test": {"code": "assay", "unit": "%", "decimals": 1},
        "criterion": {"lower": lower, "upper": upper},
        "direction": direction,
        "studies": [{"study": s, "lot": f"LOT-{s}", "start_date": "2026-01-01"} for s in studies],
        "results": results,
        "unused": [],
    }


EVALUATION = SimpleNamespace(
    unit="%",
    name="Assay",
    condition="Long-term",
    direction="decreases",
    lower_limit=Decimal("95"),
    upper_limit=Decimal("105"),
)


def test_months_of_data_are_drawn_to_a_little_past_the_estimate():
    days = (0, 91, 183, 274, 365)
    result = shelf_life.replay(content(days, [("100.2", "99.7", "99.1", "98.6", "98.0")]))
    drawing = plot.geometry(EVALUATION, result)
    estimate = result.estimate.months
    last = Decimal(drawing["x_ticks"][-1]["label"])
    assert estimate < last <= estimate * Decimal("1.05") + 5
    kinds = {mark["kind"]: mark for mark in drawing["marks"]}
    assert kinds["covered"]["text"] == "Data to 12 months"
    assert kinds["estimate"]["text"] == f"Estimate {result.estimate_months} months"
    # The data's end is far from the axis: its label sits left of its line.
    assert kinds["covered"]["anchor"] == "end"
    assert len(drawing["markers"]) == 5 and drawing["has_fit"]
    assert drawing["confidence"] == "One-sided 95 % confidence limit"
    assert [line["kind"] for line in drawing["lines"]] == ["mean", "criterion"]


def test_days_of_data_are_not_squeezed_and_labels_do_not_meet():
    result = shelf_life.replay(
        content((0, 1, 2), [("100.20", "99.90", "99.60"), ("100.10", "99.85", "99.50")])
    )
    drawing = plot.geometry(EVALUATION, result)
    assert Decimal(drawing["x_ticks"][-1]["label"]) <= 1
    spans = []
    for mark in drawing["marks"]:
        x = Decimal(mark["x"])
        span = (x - plot.LABEL_ROOM, x) if mark["anchor"] == "end" else (x, x + plot.LABEL_ROOM)
        assert span[0] >= plot.LEFT and span[1] <= plot.RIGHT + plot.LABEL_ROOM / 2, mark
        spans.append((mark["label_y"], span))
    (row_a, a), (row_b, b) = spans
    assert row_a != row_b or a[1] <= b[0] or b[1] <= a[0]  # labels never overlap
    assert len(drawing["key"]) == 2 and {item["d"] for item in drawing["key"]} == {
        plot.legend_path("circle"),
        plot.legend_path("square"),
    }


def test_an_out_of_specification_result_is_named_and_filled():
    result = shelf_life.replay(content((0, 91, 183), [("100.0", "97.0", "94.5")]))
    drawing = plot.geometry(EVALUATION, result)
    assert drawing["has_oos"]
    flagged = [m for m in drawing["markers"] if m["state"] == "oos"]
    assert len(flagged) == 1 and "outside the acceptance criterion" in flagged[0]["title"]


def test_a_limit_that_never_meets_the_criterion_draws_half_again_the_data():
    result = shelf_life.replay(content((0, 91, 183, 274), [("100.0", "100.3", "100.5", "100.8")]))
    assert result.estimate.months is None
    drawing = plot.geometry(EVALUATION, result)
    assert [mark["kind"] for mark in drawing["marks"]] == ["covered"]
    assert Decimal(drawing["x_ticks"][-1]["label"]) >= regression.months(183) * Decimal("1.5")


def test_nothing_to_draw_without_results():
    result = shelf_life.replay(content((), []))
    assert plot.geometry(EVALUATION, result) is None
