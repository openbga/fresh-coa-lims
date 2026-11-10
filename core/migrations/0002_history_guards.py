from django.db import migrations

TABLES = [
    "core_auditevent",
    "core_electronicsignature",
    "core_auditreview",
    "core_auditreview_events",
]
SQL = """
CREATE FUNCTION oq_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'Historical evidence cannot be updated or deleted'; END;
$$ LANGUAGE plpgsql;
CREATE FUNCTION oq_rule_immutable() RETURNS trigger AS $$
BEGIN
 IF OLD.status = 'approved' THEN
  RAISE EXCEPTION 'Approved rules cannot be updated or deleted';
 END IF;
 IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER rule_immutable BEFORE UPDATE OR DELETE ON core_ruleset
FOR EACH ROW EXECUTE FUNCTION oq_rule_immutable();
""" + "\n".join(
    f"CREATE TRIGGER history_immutable BEFORE UPDATE OR DELETE ON {table} "
    "FOR EACH ROW EXECUTE FUNCTION oq_immutable();"
    for table in TABLES
)
REVERSE = (
    "\n".join(f"DROP TRIGGER history_immutable ON {table};" for table in TABLES)
    + """
DROP TRIGGER rule_immutable ON core_ruleset;
DROP FUNCTION oq_rule_immutable();
DROP FUNCTION oq_immutable();
"""
)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
