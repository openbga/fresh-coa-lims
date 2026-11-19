from django.db import migrations

SQL = """
CREATE FUNCTION planning_guard_target() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Turnaround targets are append-only: a change adds a new target';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER planning_target_guard BEFORE UPDATE OR DELETE ON planning_target
FOR EACH ROW EXECUTE FUNCTION planning_guard_target();

CREATE FUNCTION planning_guard_plan() RETURNS trigger AS $$
DECLARE
  test_state text;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Test plans cannot be deleted';
  END IF;
  IF TG_OP = 'UPDATE' THEN
    IF NEW.test_id IS DISTINCT FROM OLD.test_id THEN
      RAISE EXCEPTION 'A plan stays with its test';
    END IF;
    IF NEW.revision <= OLD.revision THEN
      RAISE EXCEPTION 'A plan change advances its revision';
    END IF;
  ELSIF NEW.revision <> 0 OR NEW.due_on IS NOT NULL OR NEW.analyst_id IS NOT NULL
        OR NEW.equipment_id IS NOT NULL OR NEW.changed_by_id IS NOT NULL THEN
    RAISE EXCEPTION 'A plan starts empty';
  END IF;
  SELECT state INTO test_state FROM analytical_analyticaltest WHERE id = NEW.test_id;
  IF test_state IS DISTINCT FROM 'open' AND test_state IS DISTINCT FROM 'submitted' THEN
    RAISE EXCEPTION 'Only a test that is open or awaiting review is planned';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER planning_plan_guard BEFORE INSERT OR UPDATE OR DELETE ON planning_plan
FOR EACH ROW EXECUTE FUNCTION planning_guard_plan();
"""

REVERSE = """
DROP TRIGGER IF EXISTS planning_plan_guard ON planning_plan;
DROP FUNCTION IF EXISTS planning_guard_plan();
DROP TRIGGER IF EXISTS planning_target_guard ON planning_target;
DROP FUNCTION IF EXISTS planning_guard_target();
"""


class Migration(migrations.Migration):
    dependencies = [("planning", "0001_initial")]

    operations = [migrations.RunSQL(SQL, REVERSE)]
