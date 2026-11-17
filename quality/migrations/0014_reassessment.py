"""The reassessment of a released lot: started only on a released lot with a retest date whose
use has not ended, one open at a time, and unchanged once concluded or withdrawn. Its outcome may
give a later retest date, never after the expiry date of the lot's dates record, which the
release froze and nothing changes afterwards."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GUARDS = """
CREATE FUNCTION quality_guard_reassessment_insert() RETURNS trigger AS $$
DECLARE
  lot_state text;
BEGIN
  -- FOR SHARE: a lot is read as committed, so a reassessment never starts on a lot that is
  -- not released.
  SELECT state INTO lot_state FROM quality_lot WHERE id = NEW.lot_id FOR SHARE;
  IF lot_state IS DISTINCT FROM 'released' THEN
    RAISE EXCEPTION 'Only a released lot is reassessed';
  END IF;
  IF NEW.state IS DISTINCT FROM 'open' THEN
    RAISE EXCEPTION 'A reassessment starts open';
  END IF;
  -- The lot's dates record in force: it was frozen at release and never changes after it.
  IF NOT EXISTS (SELECT 1 FROM quality_lotdates d
                 WHERE d.lot_id = NEW.lot_id AND d.retest_on IS NOT NULL
                   AND NOT EXISTS (SELECT 1 FROM quality_lotdates c WHERE c.replaces_id = d.id)) THEN
    RAISE EXCEPTION 'Only a lot with a retest date is reassessed';
  END IF;
  IF EXISTS (SELECT 1 FROM quality_reassessment
             WHERE lot_id = NEW.lot_id AND outcome = 'not_suitable') THEN
    RAISE EXCEPTION 'The use of this lot ended with a reassessment';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reassessment_insert_guard BEFORE INSERT ON quality_reassessment
FOR EACH ROW EXECUTE FUNCTION quality_guard_reassessment_insert();

CREATE FUNCTION quality_guard_reassessment() RETURNS trigger AS $$
DECLARE
  decided text[] := ARRAY['state', 'outcome', 'retest_on', 'result_evidence', 'decided_at',
                          'decision_reason', 'revision'];
  expiry date;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Reassessments cannot be deleted';
  END IF;
  IF OLD.state <> 'open' THEN
    RAISE EXCEPTION 'A concluded or withdrawn reassessment is immutable';
  END IF;
  IF (to_jsonb(OLD) - decided) IS DISTINCT FROM (to_jsonb(NEW) - decided) THEN
    RAISE EXCEPTION 'What a reassessment examines is immutable';
  END IF;
  IF NEW.retest_on IS NOT NULL THEN
    SELECT d.expiry_on INTO expiry FROM quality_lotdates d
    WHERE d.lot_id = NEW.lot_id
      AND NOT EXISTS (SELECT 1 FROM quality_lotdates c WHERE c.replaces_id = d.id);
    IF expiry IS NOT NULL AND NEW.retest_on > expiry THEN
      RAISE EXCEPTION 'A new retest date is never after the expiry date';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER reassessment_guard BEFORE UPDATE OR DELETE ON quality_reassessment
FOR EACH ROW EXECUTE FUNCTION quality_guard_reassessment();
"""
REVERSE = """
DROP TRIGGER reassessment_guard ON quality_reassessment;
DROP FUNCTION quality_guard_reassessment();
DROP TRIGGER reassessment_insert_guard ON quality_reassessment;
DROP FUNCTION quality_guard_reassessment_insert();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0013_lot_dates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Reassessment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reason", models.TextField(help_text="Why the material is examined again.")),
                (
                    "sample_reference",
                    models.CharField(max_length=80, unique=True, verbose_name="Sample reference"),
                ),
                ("sampled_on", models.DateField(verbose_name="Date sampled")),
                ("quantity", models.DecimalField(decimal_places=4, max_digits=14)),
                (
                    "quantity_unit",
                    models.CharField(
                        choices=[
                            ("mg", "mg"),
                            ("g", "g"),
                            ("kg", "kg"),
                            ("mL", "mL"),
                            ("L", "L"),
                            ("units", "units (items)"),
                        ],
                        max_length=8,
                    ),
                ),
                (
                    "containers",
                    models.CharField(
                        help_text="Which containers of the lot were sampled, and where the material is stored.",
                        max_length=200,
                        verbose_name="Containers sampled",
                    ),
                ),
                ("dates_basis", models.JSONField()),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("concluded", "Concluded"),
                            ("withdrawn", "Withdrawn"),
                        ],
                        default="open",
                        max_length=12,
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("suitable", "Suitable for use until a new retest date"),
                            ("not_suitable", "Not suitable: its use ends"),
                        ],
                        default="",
                        max_length=14,
                    ),
                ),
                (
                    "retest_on",
                    models.DateField(blank=True, null=True, verbose_name="New retest date"),
                ),
                ("result_evidence", models.JSONField(blank=True, default=dict)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decision_reason", models.TextField(blank=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reassessments",
                        to="quality.lot",
                    ),
                ),
                (
                    "started_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("state", "open")),
                        fields=("lot",),
                        name="reassessment_one_open",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("quantity__gt", 0)), name="reassessment_quantity"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("reason__regex", "^\\s*$"), _negated=True),
                            models.Q(("sample_reference__regex", "^\\s*$"), _negated=True),
                            models.Q(("containers__regex", "^\\s*$"), _negated=True),
                        ),
                        name="reassessment_stated",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("decided_at__isnull", True),
                                ("decision_reason", ""),
                                ("outcome", ""),
                                ("result_evidence", {}),
                                ("retest_on__isnull", True),
                                ("state", "open"),
                            ),
                            models.Q(
                                ("decided_at__isnull", False),
                                ("state", "concluded"),
                                models.Q(("result_evidence", {}), _negated=True),
                                models.Q(("decision_reason__regex", "^\\s*$"), _negated=True),
                                models.Q(
                                    models.Q(("outcome", "suitable"), ("retest_on__isnull", False)),
                                    models.Q(
                                        ("outcome", "not_suitable"), ("retest_on__isnull", True)
                                    ),
                                    _connector="OR",
                                ),
                            ),
                            models.Q(
                                ("decided_at__isnull", False),
                                ("outcome", ""),
                                ("result_evidence", {}),
                                ("retest_on__isnull", True),
                                ("state", "withdrawn"),
                                models.Q(("decision_reason__regex", "^\\s*$"), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="reassessment_steps",
                    ),
                ],
            },
        ),
        migrations.RunSQL(GUARDS, REVERSE),
    ]
