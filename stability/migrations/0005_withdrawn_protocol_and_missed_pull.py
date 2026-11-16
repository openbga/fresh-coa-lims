"""A draft protocol can be withdrawn, and a pulled pull whose testing holds nothing in progress
can be recorded as missed.

A draft that names a specification which cannot state one of its tests can never be approved,
and while it is the latest version no other version of its code can be drafted: withdrawing it
is the way forward. A pull whose material cannot be tested (lost, insufficient) after it was
pulled would otherwise keep its study from being completed. Both guards are replaced: a
withdrawal changes only the state and record revision of a draft, and a pulled pull moves to
missed with its reason; everything else stays as migration 0002 guards it.
"""

from django.db import migrations, models

PROTOCOL = """
CREATE OR REPLACE FUNCTION stability_guard_protocol() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Protocol records cannot be deleted';
  END IF;
  IF OLD.state = 'draft' AND NEW.state IN ('draft', 'approved') THEN
    IF (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'content_digest')
       IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'content_digest') THEN
      RAISE EXCEPTION 'Protocol header is immutable; create a new version';
    END IF;
  {withdrawn}ELSIF OLD.state = 'approved' AND NEW.state = 'superseded' THEN
    IF (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'Approved protocol content is immutable';
    END IF;
  ELSE
    RAISE EXCEPTION 'Approved protocol content is immutable; create a new version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
WITHDRAWN = """ELSIF OLD.state = 'draft' AND NEW.state = 'withdrawn' THEN
    IF (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'A withdrawn protocol keeps its content';
    END IF;
  """

PULL = """
CREATE OR REPLACE FUNCTION stability_guard_pull() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Pull records cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'scheduled' AND NEW.state IN ('scheduled', 'pulled', 'missed'))
          OR (OLD.state = 'pulled' AND NEW.state IN ({pulled})))
     OR OLD.study_id <> NEW.study_id OR OLD.timepoint_id <> NEW.timepoint_id
     OR OLD.due_date <> NEW.due_date THEN
    RAISE EXCEPTION 'Pull identity and accepted or missed pulls are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

FORWARD = PROTOCOL.replace("{withdrawn}", WITHDRAWN) + PULL.replace(
    "{pulled}", "'pulled', 'accepted', 'missed'"
)
REVERSE = PROTOCOL.replace("{withdrawn}", "") + PULL.replace("{pulled}", "'pulled', 'accepted'")


class Migration(migrations.Migration):
    dependencies = [("stability", "0004_pull_testing")]

    operations = [
        migrations.AlterField(
            model_name="protocol",
            name="state",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("approved", "Approved"),
                    ("superseded", "Superseded"),
                    ("withdrawn", "Withdrawn"),
                ],
                default="draft",
                max_length=12,
            ),
        ),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
