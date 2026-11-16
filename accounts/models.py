from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxLengthValidator
from django.db import models


class User(AbstractUser):
    """One named identity per member of the laboratory staff."""

    management_revision = models.PositiveIntegerField(default=1, db_default=1)
    session_epoch = models.PositiveIntegerField(default=1, db_default=1)
    password_change_required = models.BooleanField(default=False, db_default=False)
    # A shared demonstration account whose password and PIN are published in the sign-in
    # announcement. Its owner cannot change them; only seed_demo --publish-accounts sets this.
    credentials_locked = models.BooleanField(default=False, db_default=False)


class LoginThrottle(models.Model):
    """Persistent consecutive password failures; an active lock refuses even a correct password."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="login_throttle"
    )
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    # Consecutive wrong second-factor codes, across locks; only an accepted code or an
    # administrator's reset clears it. At accounts.two_factor.CODE_FAILURE_LIMIT the second
    # factor stops working until an administrator resets it.
    code_failures = models.PositiveIntegerField(default=0, db_default=0)


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


class RecoveryCode(models.Model):
    """A one-time code that replaces the authenticator code at sign-in when the app is lost.

    Codes carry 120 random bits, so an approved one-way hash protects them; the code itself is
    shown once, when the set is made, and never stored. A used code keeps its row with the time
    of use until the set is replaced.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recovery_codes"
    )
    digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class SecurityKey(models.Model):
    """A security key or passkey (a WebAuthn credential) its owner uses as a sign-in factor.

    Only the public key is stored: the private key never leaves the key, the phone or the
    password manager that holds the passkey. A key works only at the host name it was registered
    at (rp_id), so a look-alike site cannot use what it answers. The name is the owner's label.
    """

    NAME_LIMIT = 60

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="security_keys"
    )
    name = models.CharField(max_length=NAME_LIMIT)
    credential_id = models.BinaryField(max_length=1023, unique=True)
    # The account's WebAuthn user handle: random, shared by the owner's keys, never personal data.
    user_handle = models.BinaryField(max_length=64)
    public_key = models.BinaryField()
    sign_count = models.PositiveBigIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    rp_id = models.CharField(max_length=253)
    # Set when the credential can be copied to other devices (a synced passkey).
    backup_eligible = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    # SHA-256 of the challenge of the last accepted use: the same response is refused again.
    last_challenge = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("name"), "user", name="security_key_name_per_user"
            ),
        ]

    def __str__(self):
        return self.name
