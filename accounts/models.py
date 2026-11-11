from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """One named identity per member of the laboratory staff."""

    management_revision = models.PositiveIntegerField(default=1)
    session_epoch = models.PositiveIntegerField(default=1)
    password_change_required = models.BooleanField(default=False)
