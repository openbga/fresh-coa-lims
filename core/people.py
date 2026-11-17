"""How the app names a person everywhere: full name, else the username; blank for nobody."""


def person(user):
    """A user's display name (``|person`` in templates, core/templatetags/ui.py)."""
    if user is None:
        return ""
    return user.get_full_name() or user.get_username()
