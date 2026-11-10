from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.services import provision_account


class Command(BaseCommand):
    help = "Provision a named staff account with audited roles; password is prompted privately."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("roles", nargs="*")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)

    def handle(self, *args, **options):
        users = get_user_model()
        try:
            actor = users.objects.get(username=options["actor"])
        except users.DoesNotExist as exc:
            raise CommandError("The provisioning actor does not exist.") from exc
        password = getpass("New staff login password: ")
        if password != getpass("Confirm login password: "):
            raise CommandError("Passwords do not match.")
        try:
            provision_account(
                actor=actor,
                username=options["username"],
                password=password,
                first_name=options["first_name"],
                last_name=options["last_name"],
                roles=options["roles"],
                reason=options["reason"],
            )
        except (PermissionDenied, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Staff account created; audit events recorded."))
