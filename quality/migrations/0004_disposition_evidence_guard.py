from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION quality_guard_lot() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Lot evidence cannot be deleted'; END IF;
  IF OLD.state = 'released' OR
     (to_jsonb(OLD) - 'state' - 'revision' - 'disposition_evidence') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision' - 'disposition_evidence') THEN
    RAISE EXCEPTION 'Lot identity and released evidence are immutable';
  END IF;
  IF NEW.disposition_evidence IS DISTINCT FROM OLD.disposition_evidence AND
     NOT (OLD.state = 'quarantine' AND NEW.state = 'released') THEN
    RAISE EXCEPTION 'Disposition evidence is captured only at release';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
REVERSE = """
CREATE OR REPLACE FUNCTION quality_guard_lot() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Lot evidence cannot be deleted'; END IF;
  IF OLD.state = 'released' OR
     (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision') THEN
    RAISE EXCEPTION 'Lot identity and released evidence are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("quality", "0003_lot_disposition_evidence")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
