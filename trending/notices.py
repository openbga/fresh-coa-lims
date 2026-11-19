"""What the QC disposition page says about trend alerts: a notice, never a blocker. Whether an
out-of-trend result holds a lot's release is the laboratory's decision, taken by the person who
signs the disposition knowing it."""

from .series import lot_alerts


def disposition_notices(lot):
    notices = []
    for point, chart, evaluation in lot_alerts(lot):
        state = (
            f"under evaluation in {evaluation.identifier}, not concluded"
            if evaluation
            else "not evaluated"
        )
        notices.append(
            f"{point.test.label} {chart.test_code} ({point.text} {chart.unit}) raised an "
            f"out-of-trend alert on {chart.identifier}, {state}. This does not block the "
            "disposition."
        )
    return notices
