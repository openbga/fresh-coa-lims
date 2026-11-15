from django.db import migrations

SQL = """
CREATE FUNCTION quality_guard_acceptance_insert() RETURNS trigger AS $$
DECLARE
  lot_state text;
  stated record;
  qualification record;
BEGIN
  IF NEW.state <> 'proposed' THEN
    RAISE EXCEPTION 'A supplier result acceptance starts as a proposal';
  END IF;
  -- FOR SHARE waits for a disposition that is updating the lot, then reads the state it
  -- committed, so a proposal cannot slip in beside a release.
  SELECT state INTO lot_state FROM quality_lot WHERE id = NEW.lot_id FOR SHARE;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Supplier results are accepted only while the lot is in quarantine';
  END IF;
  -- The certificate row lock makes a proposal wait for a correction or a withdrawal of the
  -- record it relies on, and then see it.
  SELECT r.test_code, r.requirement_hash, r.conforms, c.lot_id, c.id AS certificate_id
    INTO stated
    FROM quality_suppliercertificateresult r
    JOIN quality_suppliercertificate c ON c.id = r.certificate_id
   WHERE r.id = NEW.result_id FOR SHARE OF c;
  IF stated.lot_id IS DISTINCT FROM NEW.lot_id THEN
    RAISE EXCEPTION 'The supplier result belongs to another lot';
  END IF;
  IF stated.test_code IS DISTINCT FROM NEW.test_code
     OR stated.requirement_hash IS DISTINCT FROM NEW.requirement_hash THEN
    RAISE EXCEPTION 'The supplier result was stated for another requirement';
  END IF;
  IF NOT stated.conforms THEN
    RAISE EXCEPTION 'A supplier result that does not meet the specification is not accepted';
  END IF;
  IF EXISTS (SELECT 1 FROM quality_suppliercertificate
              WHERE corrects_id = stated.certificate_id)
     OR EXISTS (SELECT 1 FROM quality_suppliercertificatewithdrawal
                 WHERE certificate_id = stated.certificate_id) THEN
    RAISE EXCEPTION 'Only the current record of a supplier certificate can be relied on';
  END IF;
  -- FOR SHARE waits for an approval or revocation being signed, then reads what it committed.
  SELECT state, test_codes INTO qualification FROM suppliers_supplierqualification
   WHERE id = NEW.qualification_id FOR SHARE;
  IF qualification.state IS DISTINCT FROM 'approved' THEN
    RAISE EXCEPTION 'Only an approved supplier qualification can be relied on';
  END IF;
  IF NEW.test_code NOT IN (SELECT jsonb_array_elements_text(qualification.test_codes)) THEN
    RAISE EXCEPTION 'The supplier qualification does not cover this test';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_acceptance_insert_guard
BEFORE INSERT ON quality_supplierresultacceptance
FOR EACH ROW EXECUTE FUNCTION quality_guard_acceptance_insert();

CREATE FUNCTION quality_guard_acceptance() RETURNS trigger AS $$
DECLARE
  lot_state text;
  qualification_state text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Supplier result acceptances cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'proposed' AND NEW.state IN ('accepted', 'withdrawn'))
          OR (OLD.state = 'accepted' AND NEW.state = 'withdrawn'))
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'accepted_at' - 'withdrawn_by_id'
         - 'withdrawn_at' - 'withdrawal_reason')
        IS DISTINCT FROM
        (to_jsonb(NEW) - 'state' - 'revision' - 'accepted_at' - 'withdrawn_by_id'
         - 'withdrawn_at' - 'withdrawal_reason') THEN
    RAISE EXCEPTION 'A supplier result acceptance is accepted or withdrawn, never edited';
  END IF;
  -- The time of the acceptance is written once, by the signature that accepts.
  IF NEW.state <> 'accepted' AND NEW.accepted_at IS DISTINCT FROM OLD.accepted_at THEN
    RAISE EXCEPTION 'The time a supplier result was accepted cannot change';
  END IF;
  SELECT state INTO lot_state FROM quality_lot WHERE id = NEW.lot_id FOR SHARE;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Supplier result acceptances change only while the lot is in quarantine';
  END IF;
  IF NEW.state = 'accepted' THEN
    SELECT state INTO qualification_state FROM suppliers_supplierqualification
     WHERE id = NEW.qualification_id FOR SHARE;
    IF qualification_state IS DISTINCT FROM 'approved' THEN
      RAISE EXCEPTION 'Only an approved supplier qualification can be relied on';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_acceptance_guard
BEFORE UPDATE OR DELETE ON quality_supplierresultacceptance
FOR EACH ROW EXECUTE FUNCTION quality_guard_acceptance();
"""

REVERSE = """
DROP TRIGGER supplier_acceptance_guard ON quality_supplierresultacceptance;
DROP FUNCTION quality_guard_acceptance();
DROP TRIGGER supplier_acceptance_insert_guard ON quality_supplierresultacceptance;
DROP FUNCTION quality_guard_acceptance_insert();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0009_supplier_result_acceptance"),
        ("suppliers", "0004_qualification_guards"),
        ("core", "0002_history_guards"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
