"""Erase a demonstration database and seed it again.

For a public demonstration whose visitors share published accounts: a scheduled job runs this so
that the accounts, the records and the sign-in announcement return to the seed's state. It is
never part of a normal deployment. Nothing is erased unless all of these hold: the deployment
opts in with ALLOW_DEMO_RESET=true, the four demonstration credentials are set and can be
published, the database schema is exactly this release's, and the database is empty or holds the
seed's demo_admin.

The erase, the accounts and the draft configuration are one transaction. Signing never runs
inside an enclosing transaction (core.services.verify_pin), so the signed steps, the
announcement and (with DEBUG) the journey's rule approval, follow in transactions of their own.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.views.decorators.debug import sensitive_variables

from core.audit import record_event
from core.models import AuditEvent
from core.services import set_pin

from .seed_demo import (
    JOURNEY_NEEDS_DEBUG,
    MARKER,
    _pin,
    check_publishable,
    demo_deployment,
    reset_note,
)

SECRETS = ("DEMO_PASSWORD", "DEMO_PIN", "DEMO_ADMIN_PASSWORD", "DEMO_ADMIN_PIN")
ADMIN = "demo_admin"


class Command(BaseCommand):
    help = (
        "Demonstration deployments only: erase every record and account, then run seed_demo "
        "again. Requires ALLOW_DEMO_RESET=true and a database that is empty or seeded."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_false",
            dest="interactive",
            help="Do not ask for confirmation (for a scheduled job).",
        )
        parser.add_argument(
            "--journey",
            action="store_true",
            help="Seed the approved chemical rule and a result awaiting review "
            "(seed_demo --journey; needs DEBUG=true).",
        )
        parser.add_argument(
            "--publish-accounts",
            action="store_true",
            help="Show the shared demo accounts, their password and their PIN in the sign-in "
            "announcement (seed_demo --publish-accounts).",
        )

    def handle(self, *args, **options):
        if not demo_deployment():
            raise CommandError(
                "Refusing to reset: set ALLOW_DEMO_RESET=true on a demonstration deployment. "
                "Never set it where a laboratory keeps its records."
            )
        if options["journey"] and not settings.DEBUG:
            raise CommandError(JOURNEY_NEEDS_DEBUG)
        self._require_this_release()
        admin_password, admin_pin = self._credentials(options["publish_accounts"])
        with transaction.atomic():
            self._require_demo_database()
            if options["interactive"]:
                name = connection.settings_dict["NAME"]
                answer = input(
                    f"This erases every record in database {name!r}, including accounts, audit "
                    "history and issued reports, then seeds the demonstration again.\n"
                    "Type 'reset' to continue: "
                )
                if answer != "reset":
                    raise CommandError("Reset cancelled. Nothing was changed.")
            tables = self._erase()
            try:
                self._first_administrator(admin_password, admin_pin)
            except (PermissionDenied, ValidationError) as exc:
                # Domain validation messages never include supplied credentials.
                detail = " ".join(getattr(exc, "messages", [str(exc)]))
                raise CommandError(
                    f"demo_admin could not be created: {detail} Nothing was changed."
                ) from exc
            call_command("seed_demo", actor=ADMIN, stdout=self.stdout, stderr=self.stderr)
        self.stdout.write(f"Demonstration erased ({tables} tables) and seeded again.")
        if options["journey"] or options["publish_accounts"]:
            try:
                call_command(
                    "seed_demo",
                    actor=ADMIN,
                    journey=options["journey"],
                    publish_accounts=options["publish_accounts"],
                    stdout=self.stdout,
                    stderr=self.stderr,
                )
            except CommandError as exc:
                raise CommandError(
                    "The demonstration was erased and seeded, but a signed step failed: "
                    f"{exc} Run the reset again."
                ) from exc
        self.stdout.write(self.style.SUCCESS("Demonstration reset complete."))

    def _credentials(self, publish):
        """Check the four credentials before anything is erased; the reset never asks for them."""
        missing = [name for name in SECRETS if not os.environ.get(name)]
        if missing:
            raise CommandError(f"Refusing to reset: set {', '.join(missing)}.")
        password, admin_password = os.environ["DEMO_PASSWORD"], os.environ["DEMO_ADMIN_PASSWORD"]
        pin, admin_pin = _pin("DEMO_PIN", ""), _pin("DEMO_ADMIN_PIN", "")
        # demo_admin changes the announcement and the accounts, so nothing published may open it.
        if admin_pin == pin or admin_password == password:
            raise CommandError(
                "demo_admin needs a password and PIN different from the published accounts."
            )
        if publish:
            check_publishable(password, pin, reset_note())
        return admin_password, admin_pin

    def _require_this_release(self):
        """A reset from another release than the web service's would seed the wrong schema."""
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError(
                "Refusing to reset: this release has migrations the database lacks. Deploy the "
                "web service, which migrates, then run the reset from the same release."
            )
        if executor.loader.applied_migrations.keys() - executor.loader.disk_migrations.keys():
            raise CommandError(
                "Refusing to reset: the database has migrations this release does not know. "
                "Deploy this job from the same release as the web service."
            )

    def _require_demo_database(self):
        """Only an empty database, or one the seed has marked, is ever erased."""
        users = get_user_model()
        if not users.objects.exists():
            return
        admin = users.objects.filter(username=ADMIN).first()
        if (
            admin is None
            or not AuditEvent.objects.filter(
                object_type="accounts.user",
                object_id=str(admin.pk),
                action="account.created",
                reason=MARKER,
            ).exists()
        ):
            raise CommandError(
                "Refusing to reset: this database has accounts but not the seed's demo_admin, "
                "so it is not a demonstration. Nothing was changed."
            )

    def _erase(self):
        """Empty every application table. Content types and permissions describe the schema,
        not the laboratory, and running web processes cache their IDs, so they stay."""
        keep = {ContentType._meta.db_table, Permission._meta.db_table}
        tables = [
            table
            for table in connection.introspection.django_table_names(only_existing=True)
            if table not in keep
        ]
        quote = connection.ops.quote_name
        with connection.cursor() as cursor:
            # Give up rather than queue behind a long request; the next run tries again.
            cursor.execute("SET LOCAL lock_timeout = '60s'")
            # The history tables' triggers guard rows against UPDATE and DELETE. TRUNCATE of the
            # whole demonstration is the one deliberate exception and fires none of them.
            cursor.execute(f"TRUNCATE {', '.join(quote(t) for t in tables)} RESTART IDENTITY")
        return len(tables)

    @sensitive_variables()
    def _first_administrator(self, password, pin):
        """Create demo_admin, which then acts for the rest of the seed.

        No account is left to act for this one, so it is created directly: what createsuperuser
        and the bootstrap role assignment do for a laboratory, without staff or superuser
        status. The seed recognises the account by MARKER.
        """
        user = get_user_model()(username=ADMIN, first_name="Synthetic", last_name="Admin")
        validate_password(password, user)
        user.full_clean(exclude=["password"])
        user.set_password(password)
        user.save()
        user.groups.set([Group.objects.get_or_create(name="admin")[0]])
        record_event(
            actor=user,
            action="account.created",
            obj=user,
            after={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "roles": ["admin"],
            },
            reason=MARKER,
        )
        set_pin(actor=user, pin=pin, password=password)
        return user
