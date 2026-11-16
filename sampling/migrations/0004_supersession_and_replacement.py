"""Supersession of sampling plan versions and signed replacement of a lot's requirements.

Sampling plan versions gain the two supersession columns their guard (shared with the catalog,
replaced in catalog 0006) lets an approval set on an earlier approved version. A lot assignment
states whether it was assigned before testing or is a signed replacement during testing, and a
replacement keeps what it changed. Adding the columns does not fire the append-only triggers.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_supersession"),
        ("quality", "0010_supplier_result_acceptance_guards"),
        ("sampling", "0003_resample_and_deviation_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="lotassignment",
            name="origin",
            field=models.CharField(
                choices=[("assigned", "Assigned"), ("replaced", "Replaced during testing")],
                default="assigned",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="lotassignment",
            name="replacement",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="samplingplanrevision",
            name="superseded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="sampling.samplingplanrevision",
            ),
        ),
        migrations.AddField(
            model_name="samplingplanrevision",
            name="superseded_from",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="lotassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("origin", "assigned"), ("replacement__isnull", True)),
                    models.Q(
                        ("origin", "replaced"),
                        ("replacement__isnull", False),
                        ("status", "ready"),
                        ("supersedes__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="lot_assignment_replacement",
            ),
        ),
        migrations.AddConstraint(
            model_name="samplingplanrevision",
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
                name="sampling_samplingplanrevision_superseded",
            ),
        ),
    ]
