"""A test that cannot be completed is closed by a signed record, and may be repeated.

Only an open test is recorded as not completed. Only its state, its record revision and
``not_completed_record`` (what the signature froze) change on the way, and it is immutable
afterwards, like an invalidated or superseded test. The record exists exactly when the test is
not completed, and it names its schema and cause. The test that repeats it has the kind
``repeat``, is linked to it and needs no investigation; a stability pull's test can be repeated
on the material pulled. The guard of 0007 is otherwise kept as it was.
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
  IF OLD.state = 'superseded' THEN
    RAISE EXCEPTION 'Superseded tests are immutable';
  END IF;
  {not_completed}IF NEW.state = 'superseded' THEN
    IF (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'A superseded test keeps everything recorded on it';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.state = 'reviewed' THEN
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
NOT_COMPLETED = """IF OLD.state = 'not_completed' THEN
    RAISE EXCEPTION 'A test recorded as not completed is immutable';
  END IF;
  IF NEW.state = 'not_completed' THEN
    IF OLD.state <> 'open' OR
       (to_jsonb(OLD) - 'state' - 'revision' - 'not_completed_record') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision' - 'not_completed_record') THEN
      RAISE EXCEPTION 'Only an open test is recorded as not completed, keeping what it holds';
    END IF;
    IF jsonb_typeof(NEW.not_completed_record) IS DISTINCT FROM 'object'
       OR NEW.not_completed_record ->> 'schema' IS DISTINCT FROM 'oq.test-not-completed/1'
       OR coalesce(NEW.not_completed_record ->> 'cause', '') = '' THEN
      RAISE EXCEPTION 'A test not completed carries the record of why';
    END IF;
    RETURN NEW;
  END IF;
  """
FORWARD = GUARD.replace("{not_completed}", NOT_COMPLETED)
# The guard of 0007, restored before the column and the new choices are removed.
REVERSE = GUARD.replace("{not_completed}", "")


class Migration(migrations.Migration):
    dependencies = [("analytical", "0008_pull_testing")]

    operations = [
        migrations.RemoveConstraint(
            model_name="analyticaltest",
            name="analytical_retest_has_investigation",
        ),
        migrations.RemoveConstraint(
            model_name="analyticaltest",
            name="analytical_pull_test_kind",
        ),
        migrations.AddField(
            model_name="analyticaltest",
            name="not_completed_record",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="What the signed record that the test cannot be completed froze; empty for every other test",
            ),
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
                    ("repeat", "Repeat of a test not completed"),
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
                    ("not_completed", "Not completed"),
                ],
                default="open",
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("kind__in", ["original", "rerun", "revised", "repeat"]),
                    ("investigation__isnull", False),
                    _connector="OR",
                ),
                name="analytical_retest_has_investigation",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("pull__isnull", True),
                    ("kind__in", ["original", "retest", "rerun", "repeat"]),
                    _connector="OR",
                ),
                name="analytical_pull_test_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="analyticaltest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("state", "not_completed"),
                        models.Q(("not_completed_record", {}), _negated=True),
                    ),
                    models.Q(
                        models.Q(("state", "not_completed"), _negated=True),
                        ("not_completed_record", {}),
                    ),
                    _connector="OR",
                ),
                name="analytical_test_not_completed_record",
            ),
        ),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
