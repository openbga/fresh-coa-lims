"""Several scopes on a lot's requirements and the signed decision of a conflict between them.

A lot assignment names the scopes it was resolved under (rows written earlier keep their one
``scope``; the column's database default keeps inserts of the previous release working while
both run). An assignment that follows quality's decision of conflicting requirements states so
(``origin`` decided) and keeps what was decided. Adding the columns does not fire the
append-only trigger.
"""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_supersession"),
        ("quality", "0011_lot_rule_version_guard"),
        ("sampling", "0004_supersession_and_replacement"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="lotassignment",
            name="lot_assignment_replacement",
        ),
        migrations.AddField(
            model_name="lotassignment",
            name="decision",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lotassignment",
            name="scopes",
            field=models.JSONField(blank=True, db_default=[], default=list),
        ),
        migrations.AlterField(
            model_name="lotassignment",
            name="origin",
            field=models.CharField(
                choices=[
                    ("assigned", "Assigned"),
                    ("replaced", "Replaced during testing"),
                    ("decided", "Conflict decided by quality"),
                ],
                default="assigned",
                max_length=10,
            ),
        ),
        migrations.AddConstraint(
            model_name="lotassignment",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("decision__isnull", True),
                        ("origin", "assigned"),
                        ("replacement__isnull", True),
                    ),
                    models.Q(
                        ("decision__isnull", True),
                        ("origin", "replaced"),
                        ("replacement__isnull", False),
                        ("status", "ready"),
                        ("supersedes__isnull", False),
                    ),
                    models.Q(
                        ("decision__isnull", False),
                        ("origin", "decided"),
                        ("replacement__isnull", True),
                        ("status", "ready"),
                        ("supersedes__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="lot_assignment_origin",
            ),
        ),
    ]
