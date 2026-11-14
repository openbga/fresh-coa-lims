from django.db import migrations

SQL = """
CREATE TRIGGER supplier_certificate_immutable
BEFORE UPDATE OR DELETE ON quality_suppliercertificate
FOR EACH ROW EXECUTE FUNCTION oq_immutable();
CREATE TRIGGER supplier_certificate_result_immutable
BEFORE UPDATE OR DELETE ON quality_suppliercertificateresult
FOR EACH ROW EXECUTE FUNCTION oq_immutable();
CREATE TRIGGER supplier_certificate_withdrawal_immutable
BEFORE UPDATE OR DELETE ON quality_suppliercertificatewithdrawal
FOR EACH ROW EXECUTE FUNCTION oq_immutable();

CREATE FUNCTION quality_guard_certificate_insert() RETURNS trigger AS $$
DECLARE
  lot_state text;
  replaced_lot bigint;
BEGIN
  -- FOR SHARE waits for a disposition that is updating the lot, then reads the state it
  -- committed, so a certificate cannot slip in beside a release.
  SELECT state INTO lot_state FROM quality_lot WHERE id = NEW.lot_id FOR SHARE;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Supplier certificates are recorded only while the lot is in quarantine';
  END IF;
  IF NEW.corrects_id IS NOT NULL THEN
    -- The row lock makes a correction and a withdrawal of the same record wait for each other.
    SELECT lot_id INTO replaced_lot FROM quality_suppliercertificate
     WHERE id = NEW.corrects_id FOR NO KEY UPDATE;
    IF replaced_lot IS DISTINCT FROM NEW.lot_id THEN
      RAISE EXCEPTION 'A certificate correction belongs to the lot of the record it corrects';
    END IF;
    IF EXISTS (SELECT 1 FROM quality_suppliercertificatewithdrawal
                WHERE certificate_id = NEW.corrects_id) THEN
      RAISE EXCEPTION 'A withdrawn supplier certificate cannot be corrected';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_certificate_insert_guard BEFORE INSERT ON quality_suppliercertificate
FOR EACH ROW EXECUTE FUNCTION quality_guard_certificate_insert();

CREATE FUNCTION quality_guard_certificate_result_insert() RETURNS trigger AS $$
DECLARE
  allowed integer;
  lot_state text;
BEGIN
  SELECT c.result_count, l.state INTO allowed, lot_state
    FROM quality_suppliercertificate c JOIN quality_lot l ON l.id = c.lot_id
   WHERE c.id = NEW.certificate_id FOR SHARE OF l;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Supplier certificates are recorded only while the lot is in quarantine';
  END IF;
  IF (SELECT count(*) FROM quality_suppliercertificateresult
       WHERE certificate_id = NEW.certificate_id) >= allowed THEN
    RAISE EXCEPTION 'A supplier certificate holds only the results it was recorded with';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_certificate_result_insert_guard
BEFORE INSERT ON quality_suppliercertificateresult
FOR EACH ROW EXECUTE FUNCTION quality_guard_certificate_result_insert();

-- Checked when the recording transaction commits: the record then holds exactly the number of
-- results it states, and the insert guard above accepts no more afterwards.
CREATE FUNCTION quality_check_certificate_results() RETURNS trigger AS $$
BEGIN
  IF (SELECT count(*) FROM quality_suppliercertificateresult
       WHERE certificate_id = NEW.id) <> NEW.result_count THEN
    RAISE EXCEPTION 'A supplier certificate is recorded together with all of its results';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER supplier_certificate_results_complete
AFTER INSERT ON quality_suppliercertificate
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION quality_check_certificate_results();

CREATE FUNCTION quality_guard_certificate_withdrawal_insert() RETURNS trigger AS $$
DECLARE
  lot_state text;
BEGIN
  SELECT l.state INTO lot_state
    FROM quality_suppliercertificate c JOIN quality_lot l ON l.id = c.lot_id
   WHERE c.id = NEW.certificate_id FOR SHARE OF l;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Supplier certificates are withdrawn only while the lot is in quarantine';
  END IF;
  PERFORM 1 FROM quality_suppliercertificate WHERE id = NEW.certificate_id FOR NO KEY UPDATE;
  IF EXISTS (SELECT 1 FROM quality_suppliercertificate
              WHERE corrects_id = NEW.certificate_id) THEN
    RAISE EXCEPTION 'Only the current record of a supplier certificate can be withdrawn';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_certificate_withdrawal_insert_guard
BEFORE INSERT ON quality_suppliercertificatewithdrawal
FOR EACH ROW EXECUTE FUNCTION quality_guard_certificate_withdrawal_insert();
"""
REVERSE = """
DROP TRIGGER supplier_certificate_withdrawal_insert_guard
  ON quality_suppliercertificatewithdrawal;
DROP FUNCTION quality_guard_certificate_withdrawal_insert();
DROP TRIGGER supplier_certificate_results_complete ON quality_suppliercertificate;
DROP FUNCTION quality_check_certificate_results();
DROP TRIGGER supplier_certificate_result_insert_guard ON quality_suppliercertificateresult;
DROP FUNCTION quality_guard_certificate_result_insert();
DROP TRIGGER supplier_certificate_insert_guard ON quality_suppliercertificate;
DROP FUNCTION quality_guard_certificate_insert();
DROP TRIGGER supplier_certificate_withdrawal_immutable ON quality_suppliercertificatewithdrawal;
DROP TRIGGER supplier_certificate_result_immutable ON quality_suppliercertificateresult;
DROP TRIGGER supplier_certificate_immutable ON quality_suppliercertificate;
"""


class Migration(migrations.Migration):
    dependencies = [("quality", "0007_supplier_certificates"), ("core", "0002_history_guards")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
