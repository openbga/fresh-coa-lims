"""A lot in quarantine can be rejected or cancelled as received in error, by signature.

Both end the quarantine like a release: the lot guard refuses every later change of a lot that
left quarantine, and the disposition evidence changes only on the way out. A rejected or
cancelled lot carries the evidence of its decision (``decision`` names it); a released lot never
does. The rule set version guard of 0011 is kept as it was.
"""

from django.db import migrations, models

GUARD = """
CREATE OR REPLACE FUNCTION quality_guard_lot() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Lot evidence cannot be deleted'; END IF;
  IF OLD.state {closed} OR
     (to_jsonb(OLD) - 'state' - 'revision' - 'disposition_evidence' - 'rules_id') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision' - 'disposition_evidence' - 'rules_id') THEN
    RAISE EXCEPTION 'Lot identity and released evidence are immutable';
  END IF;
  IF NEW.rules_id IS DISTINCT FROM OLD.rules_id AND (
       NEW.state <> 'quarantine'
       OR (SELECT code FROM core_ruleset WHERE id = NEW.rules_id)
          IS DISTINCT FROM (SELECT code FROM core_ruleset WHERE id = OLD.rules_id)
       OR (SELECT status FROM core_ruleset WHERE id = NEW.rules_id)
          IS DISTINCT FROM 'approved') THEN
    RAISE EXCEPTION 'A lot keeps its rule set: only its approved version changes, in quarantine';
  END IF;
  IF NEW.disposition_evidence IS DISTINCT FROM OLD.disposition_evidence AND
     NOT (OLD.state = 'quarantine' AND NEW.state {decided}) THEN
    RAISE EXCEPTION 'Disposition evidence is captured only at release';
  END IF;
  {decision}RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
DECISION = """IF NEW.state IN ('rejected', 'cancelled') AND (
       jsonb_typeof(NEW.disposition_evidence) IS DISTINCT FROM 'object'
       OR NEW.disposition_evidence ->> 'decision' IS DISTINCT FROM NEW.state
       OR coalesce(NEW.disposition_evidence ->> 'schema', '') = '') THEN
    RAISE EXCEPTION 'A rejected or cancelled lot carries the evidence of its decision';
  END IF;
  IF NEW.state IN ('quarantine', 'released') AND NEW.disposition_evidence ? 'decision' THEN
    RAISE EXCEPTION 'Only a rejected or cancelled lot carries a decision';
  END IF;
  """
FORWARD = (
    GUARD.replace("{closed}", "<> 'quarantine'")
    .replace("{decided}", "IN ('released', 'rejected', 'cancelled')")
    .replace("{decision}", DECISION)
)
REVERSE = (
    GUARD.replace("{closed}", "= 'released'")
    .replace("{decided}", "= 'released'")
    .replace("{decision}", "")
)


class Migration(migrations.Migration):
    dependencies = [("quality", "0011_lot_rule_version_guard")]

    operations = [
        migrations.AlterField(
            model_name="lot",
            name="state",
            field=models.CharField(
                choices=[
                    ("quarantine", "Quarantine"),
                    ("released", "Released"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                default="quarantine",
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="lot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("state__in", ["quarantine", "released", "rejected", "cancelled"])
                ),
                name="lot_state_known",
            ),
        ),
        migrations.RunSQL(FORWARD, REVERSE),
    ]
