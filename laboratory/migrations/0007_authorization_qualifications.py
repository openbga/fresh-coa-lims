"""Qualifications for authorizing a decision that a rule set reserves (release decisions and
issuing certificates). Choices and help text only: the guard of 0002 already freezes the
``work`` and ``activity`` columns of every qualification, and the check of 0006 keeps an
instrument's qualification for performing."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("laboratory", "0006_training_and_review_qualifications"),
    ]

    operations = [
        migrations.AlterField(
            model_name="qualification",
            name="activity",
            field=models.CharField(
                help_text="Method, activity or qualification stage (e.g. IQ/OQ/PQ), or the activity a rule set names for the decisions it reserves.",
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name="qualification",
            name="work",
            field=models.CharField(
                choices=[
                    ("perform", "Performing the work"),
                    ("review", "Reviewing results"),
                    ("release", "Release decisions"),
                    ("certify", "Issuing certificates"),
                ],
                default="perform",
                max_length=8,
                verbose_name="Qualified for",
            ),
        ),
    ]
