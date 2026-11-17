from django.db import migrations

SQL = """
CREATE FUNCTION validation_guard_use_acceptance() RETURNS trigger AS $$
DECLARE
  changed text[];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Records of the intended use cannot be deleted';
  END IF;
  IF NEW.revision <> OLD.revision + 1 THEN
    RAISE EXCEPTION 'A record of the intended use advances its revision by one';
  END IF;
  IF OLD.state = 'recorded' AND NEW.state = 'accepted' THEN
    changed := ARRAY['state', 'revision', 'configuration', 'configuration_hash',
                     'accepted_release', 'accepted_at'];
  ELSIF OLD.state = 'recorded' AND NEW.state = 'withdrawn' THEN
    changed := ARRAY['state', 'revision', 'withdrawn_at'];
  ELSIF OLD.state = 'accepted' AND NEW.state = 'superseded' THEN
    IF NEW.superseded_by_id IS NULL OR NEW.superseded_by_id = NEW.id THEN
      RAISE EXCEPTION 'An acceptance is superseded by another record of the intended use';
    END IF;
    changed := ARRAY['state', 'revision', 'superseded_at', 'superseded_by_id'];
  ELSIF OLD.state = NEW.state THEN
    RAISE EXCEPTION 'A record of the intended use is immutable; withdraw it and record a new one';
  ELSE
    RAISE EXCEPTION 'A record of the intended use is accepted or withdrawn once, and an '
                    'accepted one is only superseded';
  END IF;
  IF (to_jsonb(OLD) - changed) IS DISTINCT FROM (to_jsonb(NEW) - changed) THEN
    RAISE EXCEPTION 'A record of the intended use is immutable; withdraw it and record a new one';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_use_acceptance_guard
BEFORE UPDATE OR DELETE ON validation_useacceptance
FOR EACH ROW EXECUTE FUNCTION validation_guard_use_acceptance();

CREATE FUNCTION validation_guard_use_acceptance_insert() RETURNS trigger AS $$
BEGIN
  IF NEW.state <> 'recorded' OR NEW.configuration IS NOT NULL OR NEW.configuration_hash <> ''
     OR NEW.accepted_release <> '' OR NEW.accepted_at IS NOT NULL
     OR NEW.superseded_at IS NOT NULL OR NEW.superseded_by_id IS NOT NULL
     OR NEW.withdrawn_at IS NOT NULL OR NEW.revision <> 1 THEN
    RAISE EXCEPTION 'A record of the intended use starts awaiting acceptance';
  END IF;
  -- The supported assays are a list of method codes, each a text that is not blank.
  IF jsonb_typeof(NEW.method_codes) IS DISTINCT FROM 'array'
     OR jsonb_array_length(NEW.method_codes) < 1
     OR EXISTS (SELECT 1 FROM jsonb_array_elements(NEW.method_codes) AS code
                 WHERE jsonb_typeof(code) <> 'string' OR btrim(code #>> '{}') = '') THEN
    RAISE EXCEPTION 'A record of the intended use names its supported assays';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_use_acceptance_insert_guard
BEFORE INSERT ON validation_useacceptance
FOR EACH ROW EXECUTE FUNCTION validation_guard_use_acceptance_insert();

CREATE FUNCTION validation_guard_rehearsal() RETURNS trigger AS $$
DECLARE
  changed text[];
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Rehearsal records cannot be deleted';
  END IF;
  IF NEW.revision <> OLD.revision + 1 THEN
    RAISE EXCEPTION 'A rehearsal record advances its revision by one';
  END IF;
  IF OLD.state = 'recorded' AND NEW.state = 'recorded' THEN
    changed := ARRAY['revision'];  -- evidence attached
  ELSIF OLD.state = 'recorded' AND NEW.state = 'accepted' THEN
    changed := ARRAY['state', 'revision', 'accepted_at', 'evidence'];
  ELSIF OLD.state = 'recorded' AND NEW.state = 'withdrawn' THEN
    changed := ARRAY['state', 'revision', 'withdrawn_at'];
  ELSE
    RAISE EXCEPTION 'A rehearsal record is accepted or withdrawn once';
  END IF;
  IF (to_jsonb(OLD) - changed) IS DISTINCT FROM (to_jsonb(NEW) - changed) THEN
    RAISE EXCEPTION 'A rehearsal record is immutable; withdraw it and record a new one';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_rehearsal_guard
BEFORE UPDATE OR DELETE ON validation_rehearsal
FOR EACH ROW EXECUTE FUNCTION validation_guard_rehearsal();

CREATE FUNCTION validation_guard_rehearsal_insert() RETURNS trigger AS $$
BEGIN
  IF NEW.state <> 'recorded' OR NEW.accepted_at IS NOT NULL OR NEW.evidence IS NOT NULL
     OR NEW.withdrawn_at IS NOT NULL OR NEW.revision <> 1 THEN
    RAISE EXCEPTION 'A rehearsal record starts awaiting acceptance';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_rehearsal_insert_guard
BEFORE INSERT ON validation_rehearsal
FOR EACH ROW EXECUTE FUNCTION validation_guard_rehearsal_insert();

CREATE FUNCTION validation_guard_rehearsal_file() RETURNS trigger AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Rehearsal evidence files are append-only';
  END IF;
  -- FOR SHARE waits for an acceptance or withdrawal in progress and then reads the row as
  -- it committed, so no file reaches a rehearsal that was accepted meanwhile.
  PERFORM 1 FROM validation_rehearsal
   WHERE id = NEW.rehearsal_id AND state = 'recorded' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Evidence is attached only while the rehearsal awaits acceptance';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_rehearsal_file_guard
BEFORE INSERT OR UPDATE OR DELETE ON validation_rehearsalfile
FOR EACH ROW EXECUTE FUNCTION validation_guard_rehearsal_file();

-- Each file attached advances the rehearsal's revision, so a signing page opened before it
-- was attached is refused as stale, however the row was written.
CREATE FUNCTION validation_rehearsal_file_attached() RETURNS trigger AS $$
BEGIN
  UPDATE validation_rehearsal SET revision = revision + 1 WHERE id = NEW.rehearsal_id;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER validation_rehearsal_file_revision
AFTER INSERT ON validation_rehearsalfile
FOR EACH ROW EXECUTE FUNCTION validation_rehearsal_file_attached();
"""

REVERSE = """
DROP TRIGGER validation_rehearsal_file_revision ON validation_rehearsalfile;
DROP FUNCTION validation_rehearsal_file_attached();
DROP TRIGGER validation_rehearsal_file_guard ON validation_rehearsalfile;
DROP FUNCTION validation_guard_rehearsal_file();
DROP TRIGGER validation_rehearsal_insert_guard ON validation_rehearsal;
DROP FUNCTION validation_guard_rehearsal_insert();
DROP TRIGGER validation_rehearsal_guard ON validation_rehearsal;
DROP FUNCTION validation_guard_rehearsal();
DROP TRIGGER validation_use_acceptance_insert_guard ON validation_useacceptance;
DROP FUNCTION validation_guard_use_acceptance_insert();
DROP TRIGGER validation_use_acceptance_guard ON validation_useacceptance;
DROP FUNCTION validation_guard_use_acceptance();
"""


class Migration(migrations.Migration):
    dependencies = [("validation", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
