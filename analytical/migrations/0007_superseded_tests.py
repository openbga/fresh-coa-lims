"""Tests superseded when a lot's requirements are replaced, and their repeats.

A test whose requirement is no longer one of the lot's is closed as ``superseded``: only its
state and record revision change, whatever state it was in, and it is immutable afterwards.
The test that repeats it under the new requirement has the kind ``revised``, is linked to it
and needs no investigation.
"""

from django.db import migrations, models

GUARD = """
CREATE OR REPLACE FUNCTION analytical_guard_test() RETURNS trigger AS $$
DECLARE
  mutable text[] := ARRAY['state', 'revision', 'batch_id', 'mean_value', 'reportable_value',
                          'reportable_text', 'conforms', 'evaluated_at', 'submitted_by_id'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Analytical tests cannot be deleted';
  END IF;
  IF OLD.state = 'invalidated' THEN
    RAISE EXCEPTION 'Invalidated tests are immutable';
  END IF;
  {superseded}IF OLD.state = 'reviewed' THEN
    IF NEW.state <> 'invalidated' OR
       (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'Reviewed tests are immutable except linked invalidation';
    END IF;
  ELSIF (to_jsonb(OLD) - mutable) IS DISTINCT FROM (to_jsonb(NEW) - mutable) THEN
    RAISE EXCEPTION 'Test identity and requirement snapshot are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
SUPERSEDED = """IF OLD.state = 'superseded' THEN
    RAISE EXCEPTION 'Superseded tests are immutable';
  END IF;
  IF NEW.state = 'superseded' THEN
    IF (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'A superseded test keeps everything recorded on it';
    END IF;
    RETURN NEW;
  END IF;
  """
FORWARD = GUARD.replace("{superseded}", SUPERSEDED)
REVERSE = GUARD.replace("{superseded}", "")


class Migration(migrations.Migration):
    dependencies = [
        ("analytical", "0006_raw_data_files"),
        ("quality", "0010_supplier_result_acceptance_guards"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="analyticaltest",
            name="analytical_retest_has_investigation",
        ),
        migrations.AlterField(
            model_name="analyticaltest",
            name="kind",
            field=models.CharField(
                choices=[
                    ("original", "Original"),
                    ("retest", "Retest"),
                    ("resample", "Resample"),
                    ("rerun", "Rerun after QC failure"),
                    ("revised", "Repeat under replaced requirements"),
                ],
                default="original",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="analyticaltest",
            name="state",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("submitted", "Awaiting review"),
                    ("reviewed", "Reviewed"),
                    ("invalidated", "Invalidated"),
                    ("superseded", "Superseded"),
                ],
                default="open",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("kind__in", ["original", "rerun", "revised"]),
                    ("investigation__isnull", False),
                    _connector="OR",
                ),
                name="analytical_retest_has_investigation",
            ),
        ),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
