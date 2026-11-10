from django.db import migrations

SQL = """
CREATE FUNCTION laboratory_guard_equipment() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Equipment records cannot be deleted';
  END IF;
  IF (to_jsonb(OLD) - 'state' - 'revision' - 'status_changed_by_id' - 'status_changed_at')
     IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision' - 'status_changed_by_id' - 'status_changed_at') THEN
    RAISE EXCEPTION 'Equipment identity is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER equipment_evidence_guard BEFORE UPDATE OR DELETE ON laboratory_equipment
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_equipment();

CREATE FUNCTION laboratory_guard_calibration() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Calibration evidence cannot be deleted';
  END IF;
  IF NOT (OLD.state = 'recorded' AND NEW.state = 'accepted')
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'accepted_at')
        IS DISTINCT FROM (to_jsonb(NEW) - 'state' - 'revision' - 'accepted_at') THEN
    RAISE EXCEPTION 'Calibration evidence is immutable; record a new calibration';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER calibration_evidence_guard BEFORE UPDATE OR DELETE ON laboratory_calibration
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_calibration();

CREATE FUNCTION laboratory_guard_qualification() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Qualification evidence cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'recorded' AND NEW.state = 'approved')
          OR (OLD.state = 'approved' AND NEW.state = 'revoked'))
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'revoked_at')
        IS DISTINCT FROM
        (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'revoked_at') THEN
    RAISE EXCEPTION 'Qualification evidence is immutable; record a new qualification';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER qualification_evidence_guard BEFORE UPDATE OR DELETE ON laboratory_qualification
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_qualification();

CREATE FUNCTION laboratory_guard_reagent() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Reagent lot records cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'received' AND NEW.state IN ('released', 'rejected'))
          OR (OLD.state = 'released' AND NEW.state = 'rejected'))
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'released_at')
        IS DISTINCT FROM (to_jsonb(NEW) - 'state' - 'revision' - 'released_at') THEN
    RAISE EXCEPTION 'Reagent lot provenance is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reagent_evidence_guard BEFORE UPDATE OR DELETE ON laboratory_reagentlot
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_reagent();

CREATE FUNCTION laboratory_guard_use() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Resource use evidence is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER use_evidence_guard BEFORE UPDATE OR DELETE ON laboratory_resourceuse
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_use();
"""

REVERSE = """
DROP TRIGGER use_evidence_guard ON laboratory_resourceuse;
DROP FUNCTION laboratory_guard_use();
DROP TRIGGER reagent_evidence_guard ON laboratory_reagentlot;
DROP FUNCTION laboratory_guard_reagent();
DROP TRIGGER qualification_evidence_guard ON laboratory_qualification;
DROP FUNCTION laboratory_guard_qualification();
DROP TRIGGER calibration_evidence_guard ON laboratory_calibration;
DROP FUNCTION laboratory_guard_calibration();
DROP TRIGGER equipment_evidence_guard ON laboratory_equipment;
DROP FUNCTION laboratory_guard_equipment();
"""


class Migration(migrations.Migration):
    dependencies = [("laboratory", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
