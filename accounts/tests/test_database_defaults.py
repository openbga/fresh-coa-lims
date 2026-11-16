"""A deployed 0002 database gains defaults without changing existing account state."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_defaults_upgrade_preserves_rows_and_accepts_old_instance_inserts(django_user_model):
    existing = django_user_model.objects.create_user(
        username="existing", management_revision=11, session_epoch=7, password_change_required=True
    )
    original_password = existing.password
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    old = [("accounts", "0002_user_management_revision_and_more")]
    new = [("accounts", "0003_retain_account_database_defaults")]
    columns = ("management_revision", "session_epoch", "password_change_required")

    def defaults():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name, column_default FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='accounts_user' "
                "AND column_name = ANY(%s)",
                [list(columns)],
            )
            return dict(cursor.fetchall())

    try:
        executor.migrate(old)
        assert defaults() == dict.fromkeys(columns)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        assert defaults() == {
            "management_revision": "1",
            "session_epoch": "1",
            "password_change_required": "false",
        }
        # Only these columns: the table is at 0003 here, without columns added by later migrations.
        existing.refresh_from_db(fields=[*columns, "password"])
        assert (
            existing.management_revision,
            existing.session_epoch,
            existing.password_change_required,
            existing.password,
        ) == (11, 7, True, original_password)
        # Historical 0001 knows none of the new columns and omits them in INSERT.
        old_users = executor.loader.project_state([("accounts", "0001_initial")]).apps.get_model(
            "accounts", "User"
        )
        inserted = old_users.objects.create(
            username="overlapping-old-instance", password="!unusable"
        )
        current = django_user_model.objects.only(*columns).get(pk=inserted.pk)
        assert (
            current.management_revision,
            current.session_epoch,
            current.password_change_required,
        ) == (1, 1, False)
    finally:
        MigrationExecutor(connection).migrate(leaves)
