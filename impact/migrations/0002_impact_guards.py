from django.db import migrations

SQL = """
CREATE FUNCTION impact_guard_assessment() RETURNS trigger AS $$
DECLARE
  -- What changes while the assessment is open (the revision) and on its way out (the decision).
  moving CONSTANT text[] := ARRAY['revision', 'state', 'decided_at', 'decision_reason',
                                  'evidence'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Impact assessments cannot be deleted';
  END IF;
  IF OLD.state <> 'open' THEN
    RAISE EXCEPTION 'A concluded or withdrawn impact assessment is immutable';
  END IF;
  IF (to_jsonb(OLD) - moving) IS DISTINCT FROM (to_jsonb(NEW) - moving) THEN
    RAISE EXCEPTION 'What an impact assessment is about is immutable';
  END IF;
  IF NEW.revision < OLD.revision THEN
    RAISE EXCEPTION 'An impact assessment revision never moves back';
  END IF;
  IF NEW.state = 'open' AND (NEW.decided_at IS NOT NULL OR NEW.decision_reason <> ''
                              OR NEW.evidence <> '{}'::jsonb) THEN
    RAISE EXCEPTION 'An open impact assessment has no decision';
  END IF;
  IF NEW.state = 'concluded' AND (NEW.evidence ->> 'schema') IS DISTINCT FROM
       'oq.impact-assessment/1' THEN
    RAISE EXCEPTION 'A concluded impact assessment freezes its records';
  END IF;
  IF NEW.state = 'withdrawn' AND NEW.evidence <> '{}'::jsonb THEN
    RAISE EXCEPTION 'A withdrawn impact assessment freezes nothing';
  END IF;
  IF NEW.state <> 'open' AND btrim(NEW.decision_reason) = '' THEN
    RAISE EXCEPTION 'A concluded or withdrawn impact assessment states its reason';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER impact_assessment_guard BEFORE UPDATE OR DELETE ON impact_assessment
FOR EACH ROW EXECUTE FUNCTION impact_guard_assessment();

CREATE FUNCTION impact_guard_assessment_insert() RETURNS trigger AS $$
BEGIN
  IF NEW.state IS DISTINCT FROM 'open' OR NEW.decided_at IS NOT NULL
     OR NEW.decision_reason <> '' OR NEW.evidence <> '{}'::jsonb THEN
    RAISE EXCEPTION 'An impact assessment starts open';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER impact_assessment_insert_guard BEFORE INSERT ON impact_assessment
FOR EACH ROW EXECUTE FUNCTION impact_guard_assessment_insert();

CREATE FUNCTION impact_guard_item() RETURNS trigger AS $$
DECLARE
  assessment_state text;
  decided CONSTANT text[] := ARRAY['decision', 'rationale', 'follow_up', 'follow_up_reference',
                                   'decided_by_id', 'decided_at', 'hold_id', 'revision'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Records of an impact assessment cannot be removed';
  END IF;
  -- FOR SHARE: a record is added or decided only while the assessment is open as committed,
  -- so it waits for a conclusion in progress and is then refused.
  SELECT state INTO assessment_state FROM impact_assessment
   WHERE id = NEW.assessment_id FOR SHARE;
  IF assessment_state IS DISTINCT FROM 'open' THEN
    RAISE EXCEPTION 'The impact assessment is no longer open';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.decision <> '' OR NEW.hold_id IS NOT NULL OR NEW.revision <> 1 THEN
      RAISE EXCEPTION 'A record of an impact assessment is added undecided';
    END IF;
    RETURN NEW;
  END IF;
  IF (to_jsonb(OLD) - decided) IS DISTINCT FROM (to_jsonb(NEW) - decided) THEN
    RAISE EXCEPTION 'Which record is assessed, and why, is immutable';
  END IF;
  IF OLD.hold_id IS NOT NULL AND NEW.hold_id IS DISTINCT FROM OLD.hold_id THEN
    RAISE EXCEPTION 'The hold placed through an impact assessment stays linked';
  END IF;
  IF NEW.revision <= OLD.revision THEN
    RAISE EXCEPTION 'A change to a record of an impact assessment advances its revision';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER impact_item_guard BEFORE INSERT OR UPDATE OR DELETE ON impact_item
FOR EACH ROW EXECUTE FUNCTION impact_guard_item();
"""
REVERSE = """
DROP TRIGGER impact_item_guard ON impact_item;
DROP FUNCTION impact_guard_item();
DROP TRIGGER impact_assessment_insert_guard ON impact_assessment;
DROP FUNCTION impact_guard_assessment_insert();
DROP TRIGGER impact_assessment_guard ON impact_assessment;
DROP FUNCTION impact_guard_assessment();
"""


class Migration(migrations.Migration):
    dependencies = [("impact", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
