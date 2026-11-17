"""Expiry and retest dates of a lot: append-only records, added only while the lot is in
quarantine, each correction linked to the record it replaces on the same lot."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GUARDS = """
CREATE TRIGGER lot_dates_immutable BEFORE UPDATE OR DELETE ON quality_lotdates
FOR EACH ROW EXECUTE FUNCTION oq_immutable();
CREATE FUNCTION quality_guard_dates_insert() RETURNS trigger AS $$
DECLARE
  lot_state text;
BEGIN
  -- FOR SHARE waits for a disposition that is updating the lot, then reads the state it
  -- committed, so a dates record cannot slip in beside a release.
  SELECT state INTO lot_state FROM quality_lot WHERE id = NEW.lot_id FOR SHARE;
  IF lot_state IS DISTINCT FROM 'quarantine' THEN
    RAISE EXCEPTION 'Expiry and retest dates are recorded only while the lot is in quarantine';
  END IF;
  IF NEW.replaces_id IS NOT NULL AND
     (SELECT lot_id FROM quality_lotdates WHERE id = NEW.replaces_id)
       IS DISTINCT FROM NEW.lot_id THEN
    RAISE EXCEPTION 'A correction of dates belongs to the lot of the record it replaces';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER lot_dates_insert_guard BEFORE INSERT ON quality_lotdates
FOR EACH ROW EXECUTE FUNCTION quality_guard_dates_insert();
"""
REVERSE = """
DROP TRIGGER lot_dates_insert_guard ON quality_lotdates;
DROP FUNCTION quality_guard_dates_insert();
DROP TRIGGER lot_dates_immutable ON quality_lotdates;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0012_lot_rejection"),
        ("core", "0002_history_guards"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LotDates",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("expiry_on", models.DateField(blank=True, null=True, verbose_name="Expiry date")),
                ("retest_on", models.DateField(blank=True, null=True, verbose_name="Retest date")),
                (
                    "basis",
                    models.TextField(
                        blank=True,
                        help_text="Where the dates come from: the supplier's label or certificate, or the shelf life or retest period the laboratory assigned and its reference.",
                        verbose_name="Basis",
                    ),
                ),
                ("reason", models.TextField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dates",
                        to="quality.lot",
                    ),
                ),
                (
                    "recorded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "replaces",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="replaced_by",
                        to="quality.lotdates",
                    ),
                ),
            ],
            options={
                "verbose_name": "expiry and retest dates",
                "verbose_name_plural": "expiry and retest dates",
                "ordering": ["recorded_at", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("replaces__isnull", True)),
                        fields=("lot",),
                        name="lot_dates_one_original",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("expiry_on__isnull", True),
                            ("retest_on__isnull", True),
                            ("retest_on__lte", models.F("expiry_on")),
                            _connector="OR",
                        ),
                        name="lot_dates_retest_by_expiry",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                models.Q(
                                    ("expiry_on__isnull", False),
                                    ("retest_on__isnull", False),
                                    _connector="OR",
                                ),
                                models.Q(("basis__regex", "^\\s*$"), _negated=True),
                            ),
                            models.Q(
                                ("expiry_on__isnull", True),
                                ("replaces__isnull", False),
                                ("retest_on__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="lot_dates_stated",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("reason__regex", "^\\s*$"), _negated=True),
                        name="lot_dates_reason",
                    ),
                ],
            },
        ),
        migrations.RunSQL(GUARDS, REVERSE),
    ]
