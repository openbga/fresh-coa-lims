from django.db import migrations

SQL = """
CREATE TRIGGER contract_laboratory_immutable
BEFORE UPDATE OR DELETE ON laboratory_contractlaboratory
FOR EACH ROW EXECUTE FUNCTION oq_immutable();

CREATE FUNCTION laboratory_guard_contract_approval() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Contract laboratory approvals cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'recorded' AND NEW.state = 'approved')
          OR (OLD.state = 'approved' AND NEW.state = 'revoked'))
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'revoked_at')
        IS DISTINCT FROM
        (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'revoked_at') THEN
    RAISE EXCEPTION 'Contract laboratory approval evidence is immutable; record a new approval';
  END IF;
  -- The time of the approval is written once, by the signature that approves.
  IF OLD.state = 'approved' AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION 'The time a contract laboratory approval was signed cannot change';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER contract_approval_guard BEFORE UPDATE OR DELETE ON laboratory_contractapproval
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_contract_approval();

CREATE FUNCTION laboratory_guard_contract_approval_insert() RETURNS trigger AS $$
BEGIN
  IF NEW.state <> 'recorded' OR NEW.approved_at IS NOT NULL OR NEW.revoked_at IS NOT NULL THEN
    RAISE EXCEPTION 'A contract laboratory approval starts as recorded evidence';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER contract_approval_insert_guard BEFORE INSERT ON laboratory_contractapproval
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_contract_approval_insert();

CREATE TRIGGER contract_use_immutable BEFORE UPDATE OR DELETE ON laboratory_contractuse
FOR EACH ROW EXECUTE FUNCTION oq_immutable();

CREATE FUNCTION laboratory_guard_contract_use_insert() RETURNS trigger AS $$
DECLARE
  approval laboratory_contractapproval%ROWTYPE;
BEGIN
  -- FOR SHARE waits for an approval or revocation being signed, then reads what it committed,
  -- so a report cannot be accepted beside a revocation.
  SELECT * INTO approval FROM laboratory_contractapproval
   WHERE id = NEW.approval_id FOR SHARE;
  IF approval.state IS DISTINCT FROM 'approved' THEN
    RAISE EXCEPTION 'Only an approved contract laboratory approval can be relied on';
  END IF;
  IF NEW.report_date < approval.valid_from OR NEW.report_date > approval.valid_until THEN
    RAISE EXCEPTION 'The report is dated outside the contract laboratory approval';
  END IF;
  IF lower(NEW.method_code) <> lower(approval.method_code) THEN
    RAISE EXCEPTION 'The contract laboratory approval is for another method';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER contract_use_insert_guard BEFORE INSERT ON laboratory_contractuse
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_contract_use_insert();
"""

REVERSE = """
DROP TRIGGER contract_use_insert_guard ON laboratory_contractuse;
DROP FUNCTION laboratory_guard_contract_use_insert();
DROP TRIGGER contract_use_immutable ON laboratory_contractuse;
DROP TRIGGER contract_approval_insert_guard ON laboratory_contractapproval;
DROP FUNCTION laboratory_guard_contract_approval_insert();
DROP TRIGGER contract_approval_guard ON laboratory_contractapproval;
DROP FUNCTION laboratory_guard_contract_approval();
DROP TRIGGER contract_laboratory_immutable ON laboratory_contractlaboratory;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("laboratory", "0003_contract_laboratories"),
        ("core", "0002_history_guards"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
