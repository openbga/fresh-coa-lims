from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.services import assign_roles


class Command(BaseCommand):
    help = (
        "Assign laboratory roles, recording administrator identity and reason in the audit trail."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("roles", nargs="*")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
            actor = get_user_model().objects.get(username=options["actor"])
            assign_roles(actor=actor, user=user, roles=options["roles"], reason=options["reason"])
        except (get_user_model().DoesNotExist, PermissionDenied, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Roles assigned; audit event recorded."))
