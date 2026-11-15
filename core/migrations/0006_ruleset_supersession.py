"""Supersession of approved rule versions.

Approving a later version of a rule set retires the approved versions it overlaps: each keeps
its approved content and states from when it no longer applies and which version replaced it.
The guard lets exactly those two columns change on an approved row, only to be set or brought
forward, never cleared or delayed, and only naming a later version of the same rule set. Adding nullable columns does not fire the row trigger.
"""

import django.db.models.deletion
from django.db import migrations, models

GUARD = """
CREATE OR REPLACE FUNCTION oq_rule_immutable() RETURNS trigger AS $$
BEGIN
 IF OLD.status = 'approved' THEN
  IF TG_OP = 'UPDATE'
     AND NEW.superseded_from IS NOT NULL AND NEW.superseded_by_id IS NOT NULL
     AND (OLD.superseded_from IS NULL OR NEW.superseded_from < OLD.superseded_from)
     AND (to_jsonb(OLD) - 'superseded_from' - 'superseded_by_id')
         = (to_jsonb(NEW) - 'superseded_from' - 'superseded_by_id')
     AND EXISTS (SELECT 1 FROM core_ruleset successor
                 WHERE successor.id = NEW.superseded_by_id
                   AND successor.code = OLD.code AND successor.version > OLD.version) THEN
   RETURN NEW;
  END IF;
  RAISE EXCEPTION 'Approved rules cannot be updated or deleted';
 END IF;
 IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
 IF NEW.superseded_from IS NOT NULL OR NEW.superseded_by_id IS NOT NULL THEN
  RAISE EXCEPTION 'Only an approved rule version is superseded, by the approval of a later one';
 END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""
GUARD_REVERSE = """
CREATE OR REPLACE FUNCTION oq_rule_immutable() RETURNS trigger AS $$
BEGIN
 IF OLD.status = 'approved' THEN
  RAISE EXCEPTION 'Approved rules cannot be updated or deleted';
 END IF;
 IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_alter_electronicsignature_signed_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="ruleset",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="core.ruleset",
            ),
        ),
        migrations.AddField(
            model_name="ruleset",
            name="superseded_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="ruleset",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("superseded_by__isnull", True), ("superseded_from__isnull", True)),
                    models.Q(
                        ("status", "approved"),
                        ("superseded_by__isnull", False),
                        ("superseded_from__gte", models.F("effective_from")),
                        ("superseded_from__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="rule_superseded",
            ),
        ),
        migrations.RunSQL(GUARD, GUARD_REVERSE),
    ]
