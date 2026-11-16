from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.services import reset_two_factor


class Command(BaseCommand):
    help = (
        "Remove an account's authenticator app, security keys and recovery codes, recording the "
        "administrator and reason in the audit trail. For recovery when no other administrator "
        "can sign in."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(username=options["username"])
            actor = get_user_model().objects.get(username=options["actor"])
            reset_two_factor(actor=actor, user=user, reason=options["reason"])
        except (get_user_model().DoesNotExist, PermissionDenied, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Two-factor sign-in removed; audit event recorded. Existing sessions of the "
                "account must sign in again."
            )
        )
