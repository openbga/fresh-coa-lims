from django.db import migrations

IMMUTABLE = ["sampling_samplingplan", "sampling_lotassignment", "sampling_samplingrecord"]
SQL = (
    "\n".join(
        f"CREATE TRIGGER sampling_immutable BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION oq_immutable();"
        for table in IMMUTABLE
    )
    + "\nCREATE TRIGGER revision_guard BEFORE UPDATE OR DELETE ON sampling_samplingplanrevision "
    "FOR EACH ROW EXECUTE FUNCTION catalog_guard_revision();"
)
REVERSE = "DROP TRIGGER revision_guard ON sampling_samplingplanrevision;\n" + "\n".join(
    f"DROP TRIGGER sampling_immutable ON {table};" for table in IMMUTABLE
)


class Migration(migrations.Migration):
    dependencies = [
        ("sampling", "0001_initial"),
        ("catalog", "0002_controlled_guards"),
        ("core", "0002_history_guards"),
    ]
    operations = [migrations.RunSQL(SQL, REVERSE)]
