import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

SQL = """
CREATE TRIGGER analytical_append_only BEFORE UPDATE OR DELETE ON analytical_rawdatafile
FOR EACH ROW EXECUTE FUNCTION analytical_append_only();
"""
REVERSE = "DROP TRIGGER analytical_append_only ON analytical_rawdatafile;"


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("analytical", "0005_calculations_bench"),
    ]

    operations = [
        migrations.CreateModel(
            name="RawDataFile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "filename",
                    models.CharField(help_text="Base name of the uploaded file", max_length=200),
                ),
                (
                    "content_type",
                    models.CharField(
                        blank=True,
                        help_text="Type declared by the browser; informational only",
                        max_length=100,
                    ),
                ),
                ("size", models.PositiveBigIntegerField()),
                ("sha256", models.CharField(max_length=64)),
                ("content", models.BinaryField()),
                (
                    "description",
                    models.CharField(help_text="What the file is", max_length=200),
                ),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "test",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="raw_files",
                        to="analytical.analyticaltest",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
                    ),
                ),
            ],
            options={
                "ordering": ["uploaded_at", "pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("test", "sha256"), name="analytical_rawfile_unique"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("size__gt", 0)), name="analytical_rawfile_not_empty"
                    ),
                ],
            },
        ),
        migrations.RunSQL(SQL, REVERSE),
    ]
