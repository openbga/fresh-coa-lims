from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import RuleSet
from core.services import save_rule


class Command(BaseCommand):
    help = "Create editable draft segment presets; never approve them automatically."

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)

    def handle(self, *args, **options):
        actor = get_user_model().objects.get(username=options["actor"])
        for segment in ["pharma", "supplement", "food", "chemical", "device"]:
            if not RuleSet.objects.filter(code=segment).exists():
                save_rule(
                    actor=actor,
                    code=segment,
                    segment=segment,
                    policy={
                        "required_tests": ["identity"],
                        "review_meaning": "reviewed",
                        "disposition_meaning": "approved",
                    },
                    effective_from=timezone.now(),
                    effective_until=timezone.now() + timedelta(days=365),
                    reason="Synthetic starter preset; local applicability review required.",
                )
        self.stdout.write("Five draft presets available; local review and approval required.")
