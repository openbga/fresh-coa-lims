"""The sign-in announcement: one administrator-signed notice shown before authentication.

Its text is public. Anything written here, including credentials of synthetic demonstration
accounts, is readable by every visitor and is kept in the audit trail.
"""

from django.core.exceptions import ValidationError
from django.views.decorators.debug import sensitive_variables

from core.services import require_role, sign_transition
from pagedocs.markdown import render

from .models import LoginAnnouncement

MEANING = "announcement_authorized"
ROLE = "admin"


def current_announcement():
    """The stored announcement, or an unsaved empty one before the first signed change."""
    return LoginAnnouncement.objects.filter(pk=1).first() or LoginAnnouncement(pk=1)


def published_announcement():
    return LoginAnnouncement.objects.filter(pk=1, published=True).first()


def announcement_html(announcement):
    """The text as shown to visitors: escaped first, then the page-documentation subset."""
    return render(announcement.body, heading_offset=2)


@sensitive_variables("pin")
def change_announcement(*, actor, pin, expected_revision, title, body, published, reason):
    require_role(actor, ROLE)
    title = title.strip()
    body = body.replace("\r\n", "\n").replace("\r", "\n").strip()
    if published and not body:
        raise ValidationError("Enter the announcement text before publishing it.")
    # The first change needs a row for its signature to bind. The placeholder is empty and
    # unpublished, so creating it shows nothing; the signed transition below records the content.
    announcement, _ = LoginAnnouncement.objects.get_or_create(pk=1)

    def apply(locked):
        if (locked.title, locked.body, locked.published) == (title, body, published):
            raise ValidationError("The announcement already has this text and status.")
        locked.title, locked.body, locked.published = title, body, published

    return sign_transition(
        actor=actor,
        pin=pin,
        obj=announcement,
        expected_revision=expected_revision,
        meaning=MEANING,
        reason=reason,
        permission=ROLE,
        apply=apply,
    )
