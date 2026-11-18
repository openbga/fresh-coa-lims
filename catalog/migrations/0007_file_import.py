"""An optional instrument file import on a method version.

``file_import`` is changed on a draft like the three calculation columns, so the revision guard
leaves it out of its comparison too; an approved or withdrawn version stays immutable. The
function is otherwise the one of ``0006_supersession``, which the reverse restores. Adding a
nullable column does not fire the row triggers.
"""

from django.db import migrations, models

GUARD = """
CREATE OR REPLACE FUNCTION catalog_guard_revision() RETURNS trigger AS $$
DECLARE
  parent text := CASE TG_TABLE_NAME
    WHEN 'catalog_methodrevision' THEN 'method_id'
    WHEN 'catalog_specificationrevision' THEN 'specification_id'
    ELSE 'plan_id' END;
  successor jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Controlled revisions cannot be deleted; withdraw a draft instead';
  END IF;
  IF OLD.status = 'approved'
     AND (to_jsonb(NEW) ->> 'superseded_from') IS NOT NULL
     AND (to_jsonb(NEW) ->> 'superseded_by_id') IS NOT NULL
     AND ((to_jsonb(OLD) ->> 'superseded_from') IS NULL
          OR (to_jsonb(NEW) ->> 'superseded_from')::timestamptz
             < (to_jsonb(OLD) ->> 'superseded_from')::timestamptz)
     AND (to_jsonb(OLD) - 'superseded_from' - 'superseded_by_id')
         = (to_jsonb(NEW) - 'superseded_from' - 'superseded_by_id') THEN
    EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE s.id = $1', TG_TABLE_NAME)
      INTO successor USING (to_jsonb(NEW) ->> 'superseded_by_id')::bigint;
    IF successor IS NULL
       OR (successor ->> parent) IS DISTINCT FROM (to_jsonb(OLD) ->> parent)
       OR (successor ->> 'version')::integer <= OLD.version THEN
      RAISE EXCEPTION 'A version is superseded only by a later version of the same document';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'draft' THEN
    RAISE EXCEPTION 'Approved or withdrawn revisions are immutable; create a new version';
  END IF;
  IF (to_jsonb(OLD) - 'status' - 'revision' - 'approved_content' - 'approved_hash'
        - 'calculation_formula' - 'calculation_unit' - 'calculation_decimals'
        - 'file_import')
     IS DISTINCT FROM
     (to_jsonb(NEW) - 'status' - 'revision' - 'approved_content' - 'approved_hash'
        - 'calculation_formula' - 'calculation_unit' - 'calculation_decimals'
        - 'file_import') THEN
    RAISE EXCEPTION 'Draft revision content is fixed at creation; create a new version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
GUARD_REVERSE = """
CREATE OR REPLACE FUNCTION catalog_guard_revision() RETURNS trigger AS $$
DECLARE
  parent text := CASE TG_TABLE_NAME
    WHEN 'catalog_methodrevision' THEN 'method_id'
    WHEN 'catalog_specificationrevision' THEN 'specification_id'
    ELSE 'plan_id' END;
  successor jsonb;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Controlled revisions cannot be deleted; withdraw a draft instead';
  END IF;
  IF OLD.status = 'approved'
     AND (to_jsonb(NEW) ->> 'superseded_from') IS NOT NULL
     AND (to_jsonb(NEW) ->> 'superseded_by_id') IS NOT NULL
     AND ((to_jsonb(OLD) ->> 'superseded_from') IS NULL
          OR (to_jsonb(NEW) ->> 'superseded_from')::timestamptz
             < (to_jsonb(OLD) ->> 'superseded_from')::timestamptz)
     AND (to_jsonb(OLD) - 'superseded_from' - 'superseded_by_id')
         = (to_jsonb(NEW) - 'superseded_from' - 'superseded_by_id') THEN
    EXECUTE format('SELECT to_jsonb(s) FROM %I s WHERE s.id = $1', TG_TABLE_NAME)
      INTO successor USING (to_jsonb(NEW) ->> 'superseded_by_id')::bigint;
    IF successor IS NULL
       OR (successor ->> parent) IS DISTINCT FROM (to_jsonb(OLD) ->> parent)
       OR (successor ->> 'version')::integer <= OLD.version THEN
      RAISE EXCEPTION 'A version is superseded only by a later version of the same document';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status <> 'draft' THEN
    RAISE EXCEPTION 'Approved or withdrawn revisions are immutable; create a new version';
  END IF;
  IF (to_jsonb(OLD) - 'status' - 'revision' - 'approved_content' - 'approved_hash'
        - 'calculation_formula' - 'calculation_unit' - 'calculation_decimals')
     IS DISTINCT FROM
     (to_jsonb(NEW) - 'status' - 'revision' - 'approved_content' - 'approved_hash'
        - 'calculation_formula' - 'calculation_unit' - 'calculation_decimals') THEN
    RAISE EXCEPTION 'Draft revision content is fixed at creation; create a new version';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_supersession"),
    ]

    operations = [
        migrations.AddField(
            model_name="methodrevision",
            name="file_import",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunSQL(GUARD, GUARD_REVERSE),
    ]
