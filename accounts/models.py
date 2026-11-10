from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """One named identity per member of the laboratory staff."""
