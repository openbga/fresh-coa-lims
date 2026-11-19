"""The reviewer's qualification relied on at review, frozen on the test.

Where a test's method version asks for qualified reviewers, the review records which approved
qualification to review the method the reviewer held (``review_evidence``), and the review's
signature binds it with the rest of the test. The column changes only on the way from awaiting
review to reviewed, and holds anything only on a reviewed test or one invalidated after review;
the guard of 0009 is otherwise kept as it was.
"""

import importlib

from django.db import migrations, models

PREVIOUS = importlib.import_module("analytical.migrations.0009_not_completed_tests").FORWARD
MUTABLE = "'submitted_by_id'];"
REVIEW = """IF NEW.review_evidence IS DISTINCT FROM OLD.review_evidence
     AND NOT (OLD.state = 'submitted' AND NEW.state = 'reviewed') THEN
    RAISE EXCEPTION 'The reviewer''s qualification is recorded by the review only';
  END IF;
  IF OLD.state = 'reviewed' THEN"""
assert PREVIOUS.count(MUTABLE) == 1 and PREVIOUS.count("IF OLD.state = 'reviewed' THEN") == 1
FORWARD = PREVIOUS.replace(MUTABLE, "'submitted_by_id', 'review_evidence'];").replace(
    "IF OLD.state = 'reviewed' THEN", REVIEW
)


class Migration(migrations.Migration):
    dependencies = [("analytical", "0012_instrument_readings")]

    operations = [
        migrations.AddField(
            model_name="analyticaltest",
            name="review_evidence",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="The reviewer's qualification relied on at review, where the method "
                "version asks for qualified reviewers; empty otherwise",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("review_evidence", {}),
                    ("state__in", ["reviewed", "invalidated"]),
                    _connector="OR",
                ),
                name="analytical_test_review_evidence",
            ),
        ),
        migrations.RunSQL(FORWARD, PREVIOUS),
    ]
