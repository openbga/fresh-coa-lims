"""A protocol names the specification that states its acceptance criteria, and a pull tested
in the system is accepted with an outcome and the results it rests on.

The new pull columns keep their defaults in the database, so a release that does not know them
can still insert pulls while both are running. The protocol and pull guards (0002) already
cover the new columns: a protocol header is immutable from creation, and an accepted pull
changes no more.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_supersession"),
        ("stability", "0003_pull_sample_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="protocol",
            name="specification",
            field=models.ForeignKey(
                blank=True,
                help_text="The specification whose approved version in force states the "
                "acceptance criteria of the protocol's tests. Without one, pulls are not "
                "tested in the system.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="catalog.specification",
            ),
        ),
        migrations.AddField(
            model_name="pull",
            name="outcome",
            field=models.CharField(
                blank=True,
                choices=[
                    ("conforms", "Meets the acceptance criteria"),
                    ("fails", "Does not meet the acceptance criteria"),
                ],
                db_default="",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="pull",
            name="result_evidence",
            field=models.JSONField(blank=True, db_default={}, default=dict),
        ),
        migrations.AddConstraint(
            model_name="pull",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("outcome", ""), ("result_evidence", {})),
                    models.Q(
                        ("state", "accepted"),
                        models.Q(("outcome", ""), _negated=True),
                        models.Q(("result_evidence", {}), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="pull_outcome_when_accepted",
            ),
        ),
    ]
