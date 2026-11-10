from django.db import migrations

SQL = """
CREATE FUNCTION reporting_guard_version() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Issued certificate versions are immutable; amend with a new version';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reportversion_immutable BEFORE UPDATE OR DELETE ON reporting_reportversion
FOR EACH ROW EXECUTE FUNCTION reporting_guard_version();

CREATE FUNCTION reporting_guard_report() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Certificate records cannot be deleted';
  END IF;
  IF (to_jsonb(OLD) - 'state' - 'revision' - 'version_count'
        - 'current_snapshot_hash' - 'current_pdf_sha256')
     IS DISTINCT FROM
     (to_jsonb(NEW) - 'state' - 'revision' - 'version_count'
        - 'current_snapshot_hash' - 'current_pdf_sha256') THEN
    RAISE EXCEPTION 'Certificate identity is immutable';
  END IF;
  IF NEW.version_count < OLD.version_count OR NEW.revision < OLD.revision
     OR (OLD.state = 'issued' AND NEW.state <> 'issued')
     OR (NEW.state = 'issued' AND NEW.version_count = 0) THEN
    RAISE EXCEPTION 'Certificate history cannot move backwards';
  END IF;
  IF NEW.version_count > OLD.version_count AND NOT EXISTS (
       SELECT 1 FROM reporting_reportversion v
       WHERE v.report_id = NEW.id AND v.number = NEW.version_count
         AND v.pdf_sha256 = NEW.current_pdf_sha256
         AND v.snapshot_hash = NEW.current_snapshot_hash) THEN
    RAISE EXCEPTION 'Certificate head must match its issued version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER report_guard BEFORE UPDATE OR DELETE ON reporting_report
FOR EACH ROW EXECUTE FUNCTION reporting_guard_report();
"""
REVERSE = """
DROP TRIGGER report_guard ON reporting_report;
DROP FUNCTION reporting_guard_report();
DROP TRIGGER reportversion_immutable ON reporting_reportversion;
DROP FUNCTION reporting_guard_version();
"""


class Migration(migrations.Migration):
    dependencies = [("reporting", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
