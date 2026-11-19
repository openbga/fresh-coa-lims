from django.apps import AppConfig
from django.conf import settings
from django.core import checks


def reviewer_check_configured(app_configs, **kwargs):
    """A method version can ask for reviewers qualified for the method. Without the reviewer
    check that request would be ignored without a sign, so its absence is an error."""
    if getattr(settings, "ANALYTICAL_REVIEWERS", ""):
        return []
    return [
        checks.Error(
            "ANALYTICAL_REVIEWERS names no reviewer check, so method versions that ask for "
            "qualified reviewers would be reviewed by any reviewer.",
            hint="Set ANALYTICAL_REVIEWERS = 'config.integrations.LaboratoryReviewers'.",
            id="analytical.E001",
        )
    ]


class AnalyticalConfig(AppConfig):
    name = "analytical"
    verbose_name = "Testing, QC and OOS"

    def ready(self):
        checks.register(reviewer_check_configured)
