"""Training records, and what a person's qualification is for.

A training record is immutable apart from its one acknowledgement by the trainee: only its state
(recorded to acknowledged), its revision and the acknowledgement time change, and it is never
deleted. A qualification states whether it is for performing the work or reviewing its results
(existing ones perform) and the training records it relies on; the guard of 0002 already freezes
both columns, like every other evidence column.
"""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

GUARD = """
CREATE FUNCTION laboratory_guard_training() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Training records cannot be deleted';
  END IF;
  IF NOT (OLD.state = 'recorded' AND NEW.state = 'acknowledged')
     OR (to_jsonb(OLD) - 'state' - 'revision' - 'acknowledged_at')
        IS DISTINCT FROM (to_jsonb(NEW) - 'state' - 'revision' - 'acknowledged_at') THEN
    RAISE EXCEPTION 'Training records are immutable; record a new training record';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER training_record_guard BEFORE UPDATE OR DELETE ON laboratory_trainingrecord
FOR EACH ROW EXECUTE FUNCTION laboratory_guard_training();
"""
REVERSE = """
DROP TRIGGER training_record_guard ON laboratory_trainingrecord;
DROP FUNCTION laboratory_guard_training();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("laboratory", "0005_device_connections"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrainingRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "activity",
                    models.CharField(
                        help_text="Method or activity code, as qualifications name it.",
                        max_length=120,
                    ),
                ),
                (
                    "document_ref",
                    models.CharField(
                        help_text="The controlled procedure, method or course trained on, with its revision.",
                        max_length=200,
                        verbose_name="Procedure or course",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("read", "Read and understood"),
                            ("instruction", "Instruction or demonstration"),
                            ("supervised", "Supervised practice"),
                            ("assessment", "Assessment of competence"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("completed", "Completed"),
                            ("competent", "Competent"),
                            ("not_yet_competent", "Not yet competent"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "trainer",
                    models.CharField(
                        help_text="Who gave the training or assessed it, or the provider of an outside course.",
                        max_length=160,
                        verbose_name="Trainer or assessor",
                    ),
                ),
                (
                    "completed_on",
                    models.DateField(help_text="The day the training or assessment was completed."),
                ),
                (
                    "evidence_ref",
                    models.CharField(
                        blank=True,
                        help_text="Where the signed training record, test or certificate is kept.",
                        max_length=200,
                        verbose_name="Evidence reference",
                    ),
                ),
                (
                    "evidence_url",
                    models.URLField(
                        blank=True,
                        max_length=500,
                        validators=[django.core.validators.URLValidator(schemes=["http", "https"])],
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("recorded", "Awaiting acknowledgement"),
                            ("acknowledged", "Acknowledged"),
                        ],
                        default="recorded",
                        max_length=14,
                    ),
                ),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("revision", models.PositiveIntegerField(default=1)),
            ],
            options={
                "ordering": ["-completed_on", "-id"],
            },
        ),
        migrations.AddField(
            model_name="qualification",
            name="training",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Ids of the person's acknowledged training records this evidence relies on.",
            ),
        ),
        migrations.AddField(
            model_name="qualification",
            name="work",
            field=models.CharField(
                choices=[("perform", "Performing the work"), ("review", "Reviewing results")],
                default="perform",
                max_length=8,
                verbose_name="Qualified for",
            ),
        ),
        migrations.AddConstraint(
            model_name="qualification",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("user__isnull", False),
                    models.Q(("training", []), ("work", "perform")),
                    _connector="OR",
                ),
                name="qualification_equipment_performs",
            ),
        ),
        migrations.AddField(
            model_name="trainingrecord",
            name="recorded_by",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="trainingrecord",
            name="trainee",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="trainingrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("kind", "assessment"), ("outcome__in", ["competent", "not_yet_competent"])
                    ),
                    models.Q(
                        models.Q(("kind", "assessment"), _negated=True), ("outcome", "completed")
                    ),
                    _connector="OR",
                ),
                name="training_outcome_of_kind",
            ),
        ),
        migrations.AddConstraint(
            model_name="trainingrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("acknowledged_at__isnull", True), ("state", "recorded")),
                    models.Q(("acknowledged_at__isnull", False), ("state", "acknowledged")),
                    _connector="OR",
                ),
                name="training_acknowledged_when_signed",
            ),
        ),
        migrations.RunSQL(GUARD, REVERSE),
    ]
