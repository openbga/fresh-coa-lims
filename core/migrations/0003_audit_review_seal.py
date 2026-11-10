from django.db import migrations

SQL = """
CREATE FUNCTION oq_review_membership_sealed() RETURNS trigger AS $$
BEGIN
 IF EXISTS (
  SELECT 1 FROM core_auditevent
  WHERE object_type = 'core.auditreview'
    AND object_id = NEW.auditreview_id::text
    AND action = 'audit.reviewed'
 ) THEN
  RAISE EXCEPTION 'Completed audit review membership is immutable';
 END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_review_membership_sealed BEFORE INSERT ON core_auditreview_events
FOR EACH ROW EXECUTE FUNCTION oq_review_membership_sealed();
"""
REVERSE = """
DROP TRIGGER audit_review_membership_sealed ON core_auditreview_events;
DROP FUNCTION oq_review_membership_sealed();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0002_history_guards")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
