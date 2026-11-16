"""Supersession of approved versions of methods, specifications and sampling plans.

Approving a later version retires the approved versions it overlaps. A retired version keeps
its approved content and signature and states from when it no longer applies and which version
replaced it. The guard, shared with sampling plan versions, lets exactly those two columns
change on an approved row, only to be set or brought forward, never cleared or delayed, and
only naming a later version of the same document; it reads them through ``to_jsonb`` so that it also runs on a table that has not gained the
columns yet. Adding nullable columns does not fire the row triggers.
"""

import django.db.models.deletion
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
GUARD_REVERSE = """
CREATE OR REPLACE FUNCTION catalog_guard_revision() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Controlled revisions cannot be deleted; withdraw a draft instead';
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
        ("catalog", "0005_calculations_and_resources"),
    ]

    operations = [
        migrations.AddField(
            model_name="methodrevision",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="catalog.methodrevision",
            ),
        ),
        migrations.AddField(
            model_name="methodrevision",
            name="superseded_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="specificationrevision",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="catalog.specificationrevision",
            ),
        ),
        migrations.AddField(
            model_name="specificationrevision",
            name="superseded_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="methodrevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("superseded_by__isnull", True), ("superseded_from__isnull", True)),
                    models.Q(
                        ("status", "approved"),
                        ("superseded_by__isnull", False),
                        ("superseded_from__gte", models.F("effective_from")),
                        ("superseded_from__isnull", False),
                        ("superseded_from__lt", models.F("effective_until")),
                    ),
                    _connector="OR",
                ),
                name="catalog_methodrevision_superseded",
            ),
        ),
        migrations.AddConstraint(
            model_name="specificationrevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("superseded_by__isnull", True), ("superseded_from__isnull", True)),
                    models.Q(
                        ("status", "approved"),
                        ("superseded_by__isnull", False),
                        ("superseded_from__gte", models.F("effective_from")),
                        ("superseded_from__isnull", False),
                        ("superseded_from__lt", models.F("effective_until")),
                    ),
                    _connector="OR",
                ),
                name="catalog_specificationrevision_superseded",
            ),
        ),
        migrations.RunSQL(GUARD, GUARD_REVERSE),
    ]
