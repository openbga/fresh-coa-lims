"""Readings taken from balances and meters connected to the analyst's computer.

Every reading of a test is kept as the device sent it. A reading is append-only: it is never
deleted, and only its ``observation`` is set, once, by a replicate of the same test recorded by
the person who took the reading.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GUARD = """
CREATE FUNCTION analytical_guard_instrument_reading() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Instrument readings cannot be deleted';
  END IF;
  IF TG_OP = 'UPDATE' AND (
       OLD.observation_id IS NOT NULL
       OR NEW.observation_id IS NULL
       OR (to_jsonb(OLD) - 'observation_id') IS DISTINCT FROM (to_jsonb(NEW) - 'observation_id')
     ) THEN
    RAISE EXCEPTION 'An instrument reading is immutable; a replicate records it once';
  END IF;
  IF NEW.observation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM analytical_observation o
    WHERE o.id = NEW.observation_id AND o.test_id = NEW.test_id
      AND o.recorded_by_id = NEW.read_by_id
  ) THEN
    RAISE EXCEPTION 'A reading is recorded by a replicate of its own test, by the person who took it';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER instrument_reading_guard BEFORE INSERT OR UPDATE OR DELETE
ON analytical_instrumentreading
FOR EACH ROW EXECUTE FUNCTION analytical_guard_instrument_reading();
"""
GUARD_REVERSE = """
DROP TRIGGER instrument_reading_guard ON analytical_instrumentreading;
DROP FUNCTION analytical_guard_instrument_reading();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("analytical", "0011_imported_observations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InstrumentReading",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("target", models.CharField(max_length=40)),
                (
                    "label",
                    models.CharField(
                        help_text="What was read, as the form named it", max_length=160
                    ),
                ),
                (
                    "connection",
                    models.JSONField(help_text="Data connection relied on, as it stood"),
                ),
                (
                    "request",
                    models.CharField(
                        help_text="What the browser sent to the device", max_length=200
                    ),
                ),
                (
                    "response",
                    models.TextField(help_text="What the device sent, exactly as received"),
                ),
                ("value", models.DecimalField(decimal_places=8, max_digits=20)),
                (
                    "value_text",
                    models.CharField(help_text="The number as the device wrote it", max_length=40),
                ),
                ("unit", models.CharField(max_length=40)),
                (
                    "serial_number",
                    models.CharField(
                        blank=True,
                        help_text="Serial number the device reported, if its format does",
                        max_length=40,
                    ),
                ),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                (
                    "observation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instrument_readings",
                        to="analytical.observation",
                    ),
                ),
                (
                    "read_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instrument_readings",
                        to="analytical.analyticaltest",
                    ),
                ),
            ],
            options={
                "ordering": ["read_at", "pk"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("response", ""), _negated=True),
                            models.Q(("request", ""), _negated=True),
                            models.Q(("unit", ""), _negated=True),
                            models.Q(("target", ""), _negated=True),
                        ),
                        name="analytical_reading_stated",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("observation__isnull", False)),
                        fields=("observation", "target"),
                        name="analytical_reading_once_per_value",
                    ),
                ],
            },
        ),
        migrations.RunSQL(GUARD, GUARD_REVERSE),
    ]
