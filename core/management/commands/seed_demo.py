"""Development-only synthetic fixtures, created through the application's public services."""

import os
from decimal import Decimal
from getpass import getpass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.services import ROLES, provision_account
from core.models import AuditEvent, PINCredential, RuleSet
from core.services import approve_rule, set_pin
from quality.models import Lot, Result, Sample
from quality.services import add_sample, receive_lot, record_result

MARKER = "Synthetic seed_demo account; development only."
LOT_NUMBER = "SYNTHETIC-DEMO-001"
SAMPLE_REFERENCE = "SYNTHETIC-DEMO-S001"
SEGMENTS = ("pharma", "supplement", "food", "chemical", "device")


class Command(BaseCommand):
    help = "Seed synthetic demo accounts and draft presets (DEBUG only); never reset credentials."

    def add_arguments(self, parser):
        parser.add_argument(
            "--actor", required=True, help="Existing account administrator username"
        )
        parser.add_argument(
            "--journey",
            action="store_true",
            help="Approve the synthetic chemical preset and create a result awaiting review",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo is available only with DEBUG=true.")
        users = get_user_model()
        try:
            actor = users.objects.get(username=options["actor"], is_active=True)
        except users.DoesNotExist as exc:
            raise CommandError("An existing active account administrator is required.") from exc
        if not actor.is_superuser and not actor.groups.filter(name="admin").exists():
            raise CommandError("The actor must be an account administrator.")
        existing = {}
        # Preflight the entire namespace before creating anything. An audit marker, rather than
        # a username prefix alone, establishes that this command created an account.
        for role in sorted(ROLES):
            username = f"demo_{role}"
            user = users.objects.filter(username=username).first()
            if user:
                if not AuditEvent.objects.filter(
                    object_type="accounts.user",
                    object_id=str(user.pk),
                    action="account.created",
                    reason=MARKER,
                ).exists():
                    raise CommandError(f"Refusing non-demo account collision: {username}.")
                existing[role] = user
        admin = existing.get("admin")
        for rule in RuleSet.objects.filter(code__in=SEGMENTS):
            if admin is None or rule.author_id != admin.pk:
                raise CommandError(f"Refusing non-demo rule-set collision: {rule.code}.")
        analyst = existing.get("analyst")
        lot = Lot.objects.filter(number=LOT_NUMBER).first()
        if lot and (analyst is None or lot.created_by_id != analyst.pk):
            raise CommandError("Refusing non-demo lot collision.")
        sample = Sample.objects.filter(reference=SAMPLE_REFERENCE).first()
        if sample and (lot is None or sample.lot_id != lot.pk):
            raise CommandError("Refusing non-demo sample collision.")
        password = pin = None
        if len(existing) != len(ROLES):
            password = os.environ.get("DEMO_PASSWORD") or getpass("Synthetic demo login password: ")
            pin = os.environ.get("DEMO_PIN") or getpass("Synthetic demo signature PIN: ")
            if not pin.isascii() or not pin.isdigit() or not 8 <= len(pin) <= 32:
                raise CommandError("DEMO_PIN must contain 8–32 ASCII digits.")
        try:
            with transaction.atomic():
                for role in sorted(ROLES):
                    if role not in existing:
                        user = provision_account(
                            actor=actor,
                            username=f"demo_{role}",
                            password=password,
                            first_name="Synthetic",
                            last_name=role.title(),
                            roles=[role],
                            reason=MARKER,
                        )
                        set_pin(actor=user, pin=pin, password=password)
                        existing[role] = user
                call_command("seed_rules", actor=existing["admin"].username, stdout=self.stdout)
                # Catalog authoring is scientific quality authority, not account administration.
                # This command creates drafts only; their author cannot independently approve them.
                call_command(
                    "seed_qc_profiles", actor=existing["quality"].username, stdout=self.stdout
                )
            if options["journey"]:
                self.seed_journey(existing, pin)
        except (PermissionDenied, ValidationError) as exc:
            # Domain validation messages never include supplied credentials.
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic demo ready. Existing credentials and records were preserved. "
                "Accounts: " + ", ".join(f"demo_{role}" for role in sorted(ROLES))
            )
        )

    def seed_journey(self, people, pin):
        rule = RuleSet.objects.filter(code="chemical").order_by("-version").first()
        if rule.status == "draft":
            if not PINCredential.objects.filter(user=people["quality"]).exists():
                raise CommandError("Enroll the existing demo_quality signature PIN first.")
            pin = pin or os.environ.get("DEMO_PIN") or getpass("Existing demo_quality PIN: ")
            rule = approve_rule(
                actor=people["quality"],
                pin=pin,
                rule=rule,
                expected_revision=rule.revision,
                reason="Synthetic demo policy review only.",
            )
        analyst = people["analyst"]
        with transaction.atomic():
            lot = Lot.objects.filter(number=LOT_NUMBER).first()
            if lot is None:
                lot = receive_lot(
                    actor=analyst,
                    number=LOT_NUMBER,
                    material="Synthetic reference powder",
                    rules=rule,
                    reason="Synthetic demo receipt.",
                )
            sample = Sample.objects.filter(reference=SAMPLE_REFERENCE).first()
            if sample is None:
                sample = add_sample(
                    actor=analyst,
                    lot=lot,
                    reference=SAMPLE_REFERENCE,
                    collected_at=timezone.now(),
                    reason="Synthetic demo sampling.",
                )
            if not Result.objects.filter(sample=sample, test_code="identity").exists():
                record_result(
                    actor=analyst,
                    sample=sample,
                    reason="Synthetic demo observation.",
                    test_code="identity",
                    value=Decimal("1"),
                    unit="ratio",
                    lower_limit=Decimal("0.9"),
                    upper_limit=Decimal("1.1"),
                )
        self.stdout.write("Synthetic lot available; use demo_reviewer and demo_quality to sign.")
