from django.conf import settings
from django.contrib.auth.models import AbstractUser
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
