from django.db import migrations

IDENTITIES = ["catalog_material", "catalog_method", "catalog_specification"]
REVISIONS = ["catalog_methodrevision", "catalog_specificationrevision"]
SQL = (
    """
CREATE FUNCTION catalog_guard_revision() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Controlled revisions cannot be deleted; withdraw a draft instead';
  END IF;
  IF OLD.status <> 'draft' THEN
    RAISE EXCEPTION 'Approved or withdrawn revisions are immutable; create a new version';
  END IF;
  IF (to_jsonb(OLD) - 'status' - 'revision' - 'approved_content' - 'approved_hash') IS DISTINCT FROM
     (to_jsonb(NEW) - 'status' - 'revision' - 'approved_content' - 'approved_hash') THEN
    RAISE EXCEPTION 'Draft revision content is fixed at creation; create a new version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE FUNCTION catalog_guard_test() RETURNS trigger AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') AND (
    SELECT status FROM catalog_specificationrevision WHERE id = OLD.specification_revision_id
  ) <> 'draft' THEN
    RAISE EXCEPTION 'Tests of an approved or withdrawn specification are immutable';
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') AND (
    SELECT status FROM catalog_specificationrevision WHERE id = NEW.specification_revision_id
  ) <> 'draft' THEN
    RAISE EXCEPTION 'Tests can only be added to a draft specification';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER specification_test_guard BEFORE INSERT OR UPDATE OR DELETE
ON catalog_specificationtest FOR EACH ROW EXECUTE FUNCTION catalog_guard_test();
"""
    + "\n".join(
        f"CREATE TRIGGER identity_immutable BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION oq_immutable();"
        for table in IDENTITIES
    )
    + "\n"
    + "\n".join(
        f"CREATE TRIGGER revision_guard BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION catalog_guard_revision();"
        for table in REVISIONS
    )
)
REVERSE = (
    "\n".join(f"DROP TRIGGER revision_guard ON {table};" for table in REVISIONS)
    + "\n"
    + "\n".join(f"DROP TRIGGER identity_immutable ON {table};" for table in IDENTITIES)
    + """
DROP TRIGGER specification_test_guard ON catalog_specificationtest;
DROP FUNCTION catalog_guard_test();
DROP FUNCTION catalog_guard_revision();
"""
)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial"), ("core", "0002_history_guards")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
