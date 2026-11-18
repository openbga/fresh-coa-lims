"""Data connections of balances and meters.

How readings are taken from an instrument connected to the analyst's computer. A connection is
append-only: only its end (``ended_at``, ``ended_by``) and ``revision`` change, once, and it is
never deleted.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GUARD = """
CREATE FUNCTION laboratory_guard_device_connection() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Data connections cannot be deleted';
  END IF;
  IF OLD.ended_at IS NOT NULL
     OR NEW.ended_at IS NULL
     OR (to_jsonb(OLD) - 'ended_at' - 'ended_by_id' - 'revision')
        IS DISTINCT FROM (to_jsonb(NEW) - 'ended_at' - 'ended_by_id' - 'revision') THEN
    RAISE EXCEPTION 'A data connection is immutable; it can only be ended, once';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER device_connection_guard BEFORE UPDATE OR DELETE ON laboratory_deviceconnection
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_device_connection();
"""
GUARD_REVERSE = """
DROP TRIGGER device_connection_guard ON laboratory_deviceconnection;
DROP FUNCTION laboratory_guard_device_connection();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("laboratory", "0004_contract_guards"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DeviceConnection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "device_format",
                    models.CharField(
                        choices=[
                            ("mt_sics", "MT-SICS (METTLER TOLEDO balances)"),
                            ("and_standard", "A&D standard format (A&D balances)"),
                            ("orion_star", "Orion Star A-series meters (GETMEAS, PC (CSV) output)"),
                        ],
                        max_length=20,
                        verbose_name="Output format",
                    ),
                ),
                (
                    "baud_rate",
                    models.PositiveIntegerField(
                        choices=[
                            (1200, "1200"),
                            (2400, "2400"),
                            (4800, "4800"),
                            (9600, "9600"),
                            (19200, "19200"),
                            (38400, "38400"),
                            (57600, "57600"),
                            (115200, "115200"),
                        ]
                    ),
                ),
                ("data_bits", models.PositiveSmallIntegerField(choices=[(7, "7"), (8, "8")])),
                (
                    "parity",
                    models.CharField(
                        choices=[("none", "None"), ("even", "Even"), ("odd", "Odd")], max_length=4
                    ),
                ),
                ("stop_bits", models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")])),
                (
                    "flow_control",
                    models.CharField(
                        choices=[("none", "None"), ("hardware", "Hardware (RTS/CTS)")],
                        default="none",
                        max_length=8,
                    ),
                ),
                (
                    "serial_number",
                    models.CharField(
                        blank=True,
                        help_text="As the device reports it. Required for a format that reports one: a reading from a device with another serial number is refused.",
                        max_length=40,
                    ),
                ),
                (
                    "verification_ref",
                    models.CharField(
                        help_text="Where the check that readings arrive unchanged through this connection is recorded, with its revision.",
                        max_length=200,
                        verbose_name="Verification record",
                    ),
                ),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "ended_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "equipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="connections",
                        to="laboratory.equipment",
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
            ],
            options={
                "ordering": ["-recorded_at", "-id"],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("ended_at__isnull", True)),
                        fields=("equipment",),
                        name="device_connection_one_current",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("ended_at__isnull", True), ("ended_by__isnull", True)),
                            models.Q(("ended_at__isnull", False), ("ended_by__isnull", False)),
                            _connector="OR",
                        ),
                        name="device_connection_ended_by",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("verification_ref__regex", "^\\s*$"), _negated=True),
                        name="device_connection_verified",
                    ),
                ],
            },
        ),
        migrations.RunSQL(GUARD, GUARD_REVERSE),
    ]
