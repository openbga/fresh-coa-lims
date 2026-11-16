"""Tests of a stability pull.

A test belongs to the testing of a lot (``lot`` and ``sample``) or to a stability pull
(``pull``), never both; an investigation of a stability test names no lot. Because a stability
test names no lot, nothing that reads a lot's tests, investigations or samples can count it.
The test guard (0007) already treats every identity column as immutable, the new one included.

Two insert guards keep a lineage inside one subject: a rerun or retest belongs to the lot or
the pull of the test it follows, and an investigation to the lot of its test (none for a
stability test).
"""

import django.db.models.deletion
from django.db import migrations, models

SUBJECT = """
CREATE FUNCTION analytical_test_subject() RETURNS trigger AS $$
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
CREATE TRIGGER analytical_test_subject BEFORE INSERT ON analytical_analyticaltest
FOR EACH ROW EXECUTE FUNCTION analytical_test_subject();

CREATE FUNCTION analytical_investigation_subject() RETURNS trigger AS $$
BEGIN
  IF NEW.lot_id IS DISTINCT FROM
     (SELECT lot_id FROM analytical_analyticaltest WHERE id = NEW.test_id) THEN
    RAISE EXCEPTION 'An investigation belongs to the lot of its test, or to none for a stability test';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER analytical_investigation_subject BEFORE INSERT ON analytical_investigation
FOR EACH ROW EXECUTE FUNCTION analytical_investigation_subject();
"""
REVERSE = """
DROP TRIGGER analytical_investigation_subject ON analytical_investigation;
DROP FUNCTION analytical_investigation_subject();
DROP TRIGGER analytical_test_subject ON analytical_analyticaltest;
DROP FUNCTION analytical_test_subject();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("analytical", "0007_superseded_tests"),
        ("quality", "0011_lot_rule_version_guard"),
        ("stability", "0004_pull_testing"),
    ]

    operations = [
        migrations.AddField(
            model_name="analyticaltest",
            name="pull",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tests",
                to="stability.pull",
            ),
        ),
        migrations.AlterField(
            model_name="analyticaltest",
            name="lot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="quality.lot",
            ),
        ),
        migrations.AlterField(
            model_name="analyticaltest",
            name="sample",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="quality.sample",
            ),
        ),
        migrations.AlterField(
            model_name="investigation",
            name="lot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="quality.lot",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("lot__isnull", False), ("pull__isnull", True), ("sample__isnull", False)
                    ),
                    models.Q(
                        ("lot__isnull", True), ("pull__isnull", False), ("sample__isnull", True)
                    ),
                    _connector="OR",
                ),
                name="analytical_test_subject",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "original")),
                fields=("pull", "test_code"),
                name="analytical_one_original_pull_test",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pull__isnull", True),
                    ("kind__in", ["original", "retest", "rerun"]),
                    _connector="OR",
                ),
                name="analytical_pull_test_kind",
            ),
        ),
        migrations.RunSQL(SUBJECT, REVERSE),
    ]
