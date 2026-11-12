from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxLengthValidator
from django.db import models


class User(AbstractUser):
    """One named identity per member of the laboratory staff."""

    management_revision = models.PositiveIntegerField(default=1, db_default=1)
    session_epoch = models.PositiveIntegerField(default=1, db_default=1)
    password_change_required = models.BooleanField(default=False, db_default=False)


class LoginThrottle(models.Model):
    """Persistent consecutive password failures; an active lock refuses even a correct password."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_throttle"
    )
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class LoginAnnouncement(models.Model):
    """The one notice shown on the sign-in page, to anyone, before authentication.

    A single row (id 1) that administrators change through accounts.announcements; each change
    is signed and its prior content stays in the audit trail.
    """

    BODY_LIMIT = 4000

    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True, validators=[MaxLengthValidator(BODY_LIMIT)])
    published = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="single_login_announcement"),
            models.CheckConstraint(
                condition=models.Q(published=False) | ~models.Q(body=""),
                name="published_login_announcement_has_text",
                violation_error_message="Enter the announcement text before publishing it.",
            ),
        ]

    def __str__(self):
        return "Sign-in announcement"
