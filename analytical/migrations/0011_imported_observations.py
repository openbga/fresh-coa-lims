"""Replicates imported from an instrument export.

An imported observation names the raw-data file of its test it was read from and keeps the row
and the cells as read. The observation table stays append-only (``0002_evidence_guards``);
adding the columns does not fire its row triggers.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# An imported replicate is read from a raw-data file of its own test.
SAME_TEST = """
CREATE FUNCTION analytical_observation_source_test() RETURNS trigger AS $$
BEGIN
  IF NEW.source_file_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM analytical_rawdatafile f
    WHERE f.id = NEW.source_file_id AND f.test_id = NEW.test_id
  ) THEN
    RAISE EXCEPTION 'An imported observation is read from a raw-data file of its own test';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER analytical_observation_source_test BEFORE INSERT ON analytical_observation
FOR EACH ROW EXECUTE FUNCTION analytical_observation_source_test();
"""
SAME_TEST_REVERSE = """
DROP TRIGGER analytical_observation_source_test ON analytical_observation;
DROP FUNCTION analytical_observation_source_test();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("analytical", "0010_reassessment_tests"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="observation",
            name="source",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Row of the instrument export and the cells read from it; empty when entered by hand",
            ),
        ),
        migrations.AddField(
            model_name="observation",
            name="source_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="imported_observations",
                to="analytical.rawdatafile",
            ),
        ),
        migrations.AddConstraint(
            model_name="observation",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("source_file__isnull", True), ("source", {})),
                    models.Q(
                        ("source_file__isnull", False),
                        models.Q(("source", {}), _negated=True),
                        ("supersedes__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="analytical_observation_source",
            ),
        ),
        migrations.RunSQL(SAME_TEST, SAME_TEST_REVERSE),
    ]
