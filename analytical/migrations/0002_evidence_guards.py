from django.db import migrations

APPEND_ONLY = ["analytical_observation", "analytical_qcresult", "analytical_investigationentry"]

SQL = """
CREATE FUNCTION analytical_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Analytical evidence is append-only; add a linked correction';
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION analytical_guard_test() RETURNS trigger AS $$
DECLARE
  mutable text[] := ARRAY['state', 'revision', 'batch_id', 'mean_value', 'reportable_value',
                          'conforms', 'evaluated_at', 'submitted_by_id'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Analytical tests cannot be deleted';
  END IF;
  IF OLD.state = 'invalidated' THEN
    RAISE EXCEPTION 'Invalidated tests are immutable';
  END IF;
  IF OLD.state = 'reviewed' THEN
    IF NEW.state <> 'invalidated' OR
       (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'Reviewed tests are immutable except linked invalidation';
    END IF;
  ELSIF (to_jsonb(OLD) - mutable) IS DISTINCT FROM (to_jsonb(NEW) - mutable) THEN
    RAISE EXCEPTION 'Test identity and requirement snapshot are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER analytical_test_guard BEFORE UPDATE OR DELETE ON analytical_analyticaltest
FOR EACH ROW EXECUTE FUNCTION analytical_guard_test();

CREATE FUNCTION analytical_guard_batch() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'QC batches cannot be deleted';
  END IF;
  IF OLD.state = 'rejected' OR
     (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision') THEN
    RAISE EXCEPTION 'QC batch identity, method snapshot and rejected batches are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER analytical_batch_guard BEFORE UPDATE OR DELETE ON analytical_qcbatch
FOR EACH ROW EXECUTE FUNCTION analytical_guard_batch();

CREATE FUNCTION analytical_guard_investigation() RETURNS trigger AS $$
DECLARE
  mutable text[] := ARRAY['phase', 'outcome', 'assignable_cause', 'conclusion', 'closed_at',
                          'revision'];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Investigations cannot be deleted';
  END IF;
  IF OLD.phase = 'closed' OR
     (to_jsonb(OLD) - mutable) IS DISTINCT FROM (to_jsonb(NEW) - mutable) THEN
    RAISE EXCEPTION 'Closed investigations and investigation identity are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER analytical_investigation_guard BEFORE UPDATE OR DELETE ON analytical_investigation
FOR EACH ROW EXECUTE FUNCTION analytical_guard_investigation();
""" + "\n".join(
    f"CREATE TRIGGER analytical_append_only BEFORE UPDATE OR DELETE ON {table} "
    "FOR EACH ROW EXECUTE FUNCTION analytical_append_only();"
    for table in APPEND_ONLY
)

REVERSE = (
    "\n".join(f"DROP TRIGGER analytical_append_only ON {t};" for t in APPEND_ONLY)
    + """
DROP TRIGGER analytical_investigation_guard ON analytical_investigation;
DROP FUNCTION analytical_guard_investigation();
DROP TRIGGER analytical_batch_guard ON analytical_qcbatch;
DROP FUNCTION analytical_guard_batch();
DROP TRIGGER analytical_test_guard ON analytical_analyticaltest;
DROP FUNCTION analytical_guard_test();
DROP FUNCTION analytical_append_only();
"""
)


class Migration(migrations.Migration):
    dependencies = [("analytical", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
