"""A lot in quarantine can move to another approved version of its own rule set.

The signed replacement of a lot's requirements applies the version of the lot's rule set now in
force. The lot guard keeps every other identity column fixed, refuses another rule set, a
version that is not approved, and any change once the lot is released.
"""

from django.db import migrations

GUARD = """
CREATE OR REPLACE FUNCTION quality_guard_lot() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Lot evidence cannot be deleted'; END IF;
  IF OLD.state = 'released' OR
     (to_jsonb(OLD) - 'state' - 'revision' - 'disposition_evidence'{rules}) IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision' - 'disposition_evidence'{rules}) THEN
    RAISE EXCEPTION 'Lot identity and released evidence are immutable';
  END IF;
  {version}IF NEW.disposition_evidence IS DISTINCT FROM OLD.disposition_evidence AND
     NOT (OLD.state = 'quarantine' AND NEW.state = 'released') THEN
    RAISE EXCEPTION 'Disposition evidence is captured only at release';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
VERSION = """IF NEW.rules_id IS DISTINCT FROM OLD.rules_id AND (
       NEW.state <> 'quarantine'
       OR (SELECT code FROM core_ruleset WHERE id = NEW.rules_id)
          IS DISTINCT FROM (SELECT code FROM core_ruleset WHERE id = OLD.rules_id)
       OR (SELECT status FROM core_ruleset WHERE id = NEW.rules_id)
          IS DISTINCT FROM 'approved') THEN
    RAISE EXCEPTION 'A lot keeps its rule set: only its approved version changes, in quarantine';
  END IF;
  """
FORWARD = GUARD.replace("{rules}", " - 'rules_id'").replace("{version}", VERSION)
REVERSE = GUARD.replace("{rules}", "").replace("{version}", "")


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0010_supplier_result_acceptance_guards"),
        ("core", "0006_ruleset_supersession"),
    ]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
