from django.db import migrations

SQL = """
CREATE FUNCTION stability_guard_protocol() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Protocol records cannot be deleted';
  END IF;
  IF OLD.state = 'draft' AND NEW.state IN ('draft', 'approved') THEN
    IF (to_jsonb(OLD) - 'state' - 'revision' - 'approved_at' - 'content_digest')
       IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision' - 'approved_at' - 'content_digest') THEN
      RAISE EXCEPTION 'Protocol header is immutable; create a new version';
    END IF;
  ELSIF OLD.state = 'approved' AND NEW.state = 'superseded' THEN
    IF (to_jsonb(OLD) - 'state' - 'revision') IS DISTINCT FROM
       (to_jsonb(NEW) - 'state' - 'revision') THEN
      RAISE EXCEPTION 'Approved protocol content is immutable';
    END IF;
  ELSE
    RAISE EXCEPTION 'Approved protocol content is immutable; create a new version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER protocol_evidence_guard BEFORE UPDATE OR DELETE ON stability_protocol
FOR EACH ROW EXECUTE FUNCTION stability_guard_protocol();

CREATE FUNCTION stability_guard_protocol_child() RETURNS trigger AS $$
BEGIN
  IF TG_OP <> 'INSERT' THEN
    RAISE EXCEPTION 'Protocol content is immutable';
  END IF;
  IF (SELECT state FROM stability_protocol WHERE id = NEW.protocol_id) <> 'draft' THEN
    RAISE EXCEPTION 'Only a draft protocol accepts new content';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER condition_evidence_guard BEFORE INSERT OR UPDATE OR DELETE
ON stability_protocolcondition
FOR EACH ROW EXECUTE FUNCTION stability_guard_protocol_child();
CREATE TRIGGER timepoint_evidence_guard BEFORE INSERT OR UPDATE OR DELETE
ON stability_protocoltimepoint
FOR EACH ROW EXECUTE FUNCTION stability_guard_protocol_child();

CREATE FUNCTION stability_guard_study() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Study records cannot be deleted';
  END IF;
  IF OLD.state <> 'active'
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'closed_at')
        IS DISTINCT FROM (to_jsonb(NEW) - 'state' - 'revision' - 'closed_at') THEN
    RAISE EXCEPTION 'Study identity and closed studies are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER study_evidence_guard BEFORE UPDATE OR DELETE ON stability_study
FOR EACH ROW EXECUTE FUNCTION stability_guard_study();

CREATE FUNCTION stability_guard_pull() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Pull records cannot be deleted';
  END IF;
  IF NOT ((OLD.state = 'scheduled' AND NEW.state IN ('scheduled', 'pulled', 'missed'))
          OR (OLD.state = 'pulled' AND NEW.state IN ('pulled', 'accepted')))
     OR OLD.study_id <> NEW.study_id OR OLD.timepoint_id <> NEW.timepoint_id
     OR OLD.due_date <> NEW.due_date THEN
    RAISE EXCEPTION 'Pull identity and accepted or missed pulls are immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER pull_evidence_guard BEFORE UPDATE OR DELETE ON stability_pull
FOR EACH ROW EXECUTE FUNCTION stability_guard_pull();

CREATE FUNCTION stability_guard_reserve() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Reserve sample records are immutable';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reserve_evidence_guard BEFORE UPDATE OR DELETE ON stability_reservesample
FOR EACH ROW EXECUTE FUNCTION stability_guard_reserve();

CREATE FUNCTION stability_guard_obligation() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Retention obligations cannot be deleted';
  END IF;
  IF OLD.anchor_date IS NOT NULL OR NEW.anchor_date IS NULL
     OR (to_jsonb(OLD) - 'anchor_date' - 'anchor_set_by_id' - 'anchor_set_at')
        IS DISTINCT FROM
        (to_jsonb(NEW) - 'anchor_date' - 'anchor_set_by_id' - 'anchor_set_at') THEN
    RAISE EXCEPTION 'Retention obligations are append-only; the anchor can be set once';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER obligation_evidence_guard BEFORE UPDATE OR DELETE ON stability_retentionobligation
FOR EACH ROW EXECUTE FUNCTION stability_guard_obligation();

CREATE FUNCTION stability_guard_hold() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Hold records cannot be deleted';
  END IF;
  IF OLD.state <> 'active' OR NEW.state NOT IN ('active', 'released')
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'released_at')
        IS DISTINCT FROM (to_jsonb(NEW) - 'state' - 'revision' - 'released_at') THEN
    RAISE EXCEPTION 'Hold history is immutable; only an active hold can be released';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER hold_evidence_guard BEFORE UPDATE OR DELETE ON stability_hold
FOR EACH ROW EXECUTE FUNCTION stability_guard_hold();
"""

REVERSE = """
DROP TRIGGER hold_evidence_guard ON stability_hold;
DROP FUNCTION stability_guard_hold();
DROP TRIGGER obligation_evidence_guard ON stability_retentionobligation;
DROP FUNCTION stability_guard_obligation();
DROP TRIGGER reserve_evidence_guard ON stability_reservesample;
DROP FUNCTION stability_guard_reserve();
DROP TRIGGER pull_evidence_guard ON stability_pull;
DROP FUNCTION stability_guard_pull();
DROP TRIGGER study_evidence_guard ON stability_study;
DROP FUNCTION stability_guard_study();
DROP TRIGGER timepoint_evidence_guard ON stability_protocoltimepoint;
DROP TRIGGER condition_evidence_guard ON stability_protocolcondition;
DROP FUNCTION stability_guard_protocol_child();
DROP TRIGGER protocol_evidence_guard ON stability_protocol;
DROP FUNCTION stability_guard_protocol();
"""


class Migration(migrations.Migration):
    dependencies = [("stability", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
