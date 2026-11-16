from django.db import migrations

SQL = """
CREATE FUNCTION suppliers_guard_qualification() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Supplier qualifications cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'recorded' AND NEW.state = 'approved')
          OR (OLD.state = 'approved' AND NEW.state = 'revoked'))
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'revoked_at')
        IS DISTINCT FROM
        (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'revoked_at') THEN
    RAISE EXCEPTION 'Supplier qualification evidence is immutable; record a new qualification';
  END IF;
  -- The time of the approval is written once, by the signature that approves.
  IF OLD.state = 'approved' AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION 'The time a supplier qualification was signed cannot change';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_qualification_guard
BEFORE UPDATE OR DELETE ON suppliers_supplierqualification
FOR EACH ROW EXECUTE FUNCTION suppliers_guard_qualification();

CREATE FUNCTION suppliers_guard_qualification_insert() RETURNS trigger AS $$
BEGIN
  IF NEW.state <> 'recorded' OR NEW.approved_at IS NOT NULL OR NEW.revoked_at IS NOT NULL THEN
    RAISE EXCEPTION 'A supplier qualification starts as recorded evidence';
  END IF;
  -- The scope is a list of test codes, each a text that is not blank, at least one.
  IF jsonb_typeof(NEW.test_codes) IS DISTINCT FROM 'array'
     OR jsonb_array_length(NEW.test_codes) < 1
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.test_codes) AS code
                 WHERE jsonb_typeof(code) <> 'string' OR btrim(code #>> '{}') = '') THEN
    RAISE EXCEPTION 'A supplier qualification names the tests it covers';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER supplier_qualification_insert_guard
BEFORE INSERT ON suppliers_supplierqualification
FOR EACH ROW EXECUTE FUNCTION suppliers_guard_qualification_insert();
"""

REVERSE = """
DROP TRIGGER supplier_qualification_insert_guard ON suppliers_supplierqualification;
DROP FUNCTION suppliers_guard_qualification_insert();
DROP TRIGGER supplier_qualification_guard ON suppliers_supplierqualification;
DROP FUNCTION suppliers_guard_qualification();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("suppliers", "0003_supplier_qualification"),
        ("core", "0002_history_guards"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
