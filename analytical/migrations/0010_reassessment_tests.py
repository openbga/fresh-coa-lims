"""Tests of a reassessment of a released lot.

A test belongs to the testing of a lot, to a stability pull or to a reassessment, never to
two. Like a pull's test, a reassessment's test names no lot, so nothing that reads a lot's
tests counts it. A linked test (rerun, retest, repeat) stays with the subject of the test it
follows. The test guard (0009) treats every column it does not name as immutable, the new one
included.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SUBJECT = """
CREATE OR REPLACE FUNCTION analytical_test_subject() RETURNS trigger AS $$
DECLARE
  followed record;
BEGIN
  IF NEW.parent_id IS NOT NULL THEN
    SELECT lot_id, pull_id, reassessment_id INTO followed
    FROM analytical_analyticaltest WHERE id = NEW.parent_id;
    IF followed.lot_id IS DISTINCT FROM NEW.lot_id
       OR followed.pull_id IS DISTINCT FROM NEW.pull_id
       OR followed.reassessment_id IS DISTINCT FROM NEW.reassessment_id THEN
      RAISE EXCEPTION 'A linked test belongs to the lot, stability pull or reassessment of the test it follows';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
REVERSE = """
CREATE OR REPLACE FUNCTION analytical_test_subject() RETURNS trigger AS $$
DECLARE
  followed record;
BEGIN
  IF NEW.parent_id IS NOT NULL THEN
    SELECT lot_id, pull_id INTO followed FROM analytical_analyticaltest WHERE id = NEW.parent_id;
    IF followed.lot_id IS DISTINCT FROM NEW.lot_id
       OR followed.pull_id IS DISTINCT FROM NEW.pull_id THEN
      RAISE EXCEPTION 'A linked test belongs to the lot or stability pull of the test it follows';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("analytical", "0009_not_completed_tests"),
        ("quality", "0014_reassessment"),
        ("stability", "0005_withdrawn_protocol_and_missed_pull"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="analyticaltest",
            name="analytical_test_subject",
        ),
        migrations.AddField(
            model_name="analyticaltest",
            name="reassessment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tests",
                to="quality.reassessment",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("lot__isnull", False),
                        ("pull__isnull", True),
                        ("reassessment__isnull", True),
                        ("sample__isnull", False),
                    ),
                    models.Q(
                        ("lot__isnull", True),
                        ("pull__isnull", False),
                        ("reassessment__isnull", True),
                        ("sample__isnull", True),
                    ),
                    models.Q(
                        ("lot__isnull", True),
                        ("pull__isnull", True),
                        ("reassessment__isnull", False),
                        ("sample__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="analytical_test_subject_of_three",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "original")),
                fields=("reassessment", "test_code"),
                name="analytical_one_original_reassessment_test",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("reassessment__isnull", True),
                    ("kind__in", ["original", "retest", "rerun", "repeat"]),
                    _connector="OR",
                ),
                name="analytical_reassessment_test_kind",
            ),
        ),
        migrations.RunSQL(SUBJECT, REVERSE),
    ]
