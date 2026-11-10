from django.db import migrations

SQL = """
CREATE FUNCTION quality_guard_result() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Result evidence cannot be deleted';
  END IF;
  IF OLD.state = 'reviewed' OR
     (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision') THEN
    RAISE EXCEPTION 'Result evidence is immutable; use a new linked correction';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER result_evidence_guard BEFORE UPDATE OR DELETE ON quality_result
FOR EACH ROW EXECUTE FUNCTION quality_guard_result();
CREATE FUNCTION quality_guard_lot() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Lot evidence cannot be deleted';
  END IF;
  IF OLD.state = 'released' OR
     (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision') THEN
    RAISE EXCEPTION 'Lot identity and released evidence are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER lot_evidence_guard BEFORE UPDATE OR DELETE ON quality_lot
FOR EACH ROW EXECUTE FUNCTION quality_guard_lot();
CREATE FUNCTION quality_guard_sample() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Sample evidence is immutable';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER sample_evidence_guard BEFORE UPDATE OR DELETE ON quality_sample
FOR EACH ROW EXECUTE FUNCTION quality_guard_sample();
"""
REVERSE = """
DROP TRIGGER sample_evidence_guard ON quality_sample;
DROP FUNCTION quality_guard_sample();
DROP TRIGGER lot_evidence_guard ON quality_lot;
DROP FUNCTION quality_guard_lot();
DROP TRIGGER result_evidence_guard ON quality_result;
DROP FUNCTION quality_guard_result();
"""


class Migration(migrations.Migration):
    dependencies = [("quality", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
