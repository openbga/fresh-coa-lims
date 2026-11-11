"""Response headers and error-report redaction shared by every page."""

import logging
import re
from functools import lru_cache

from django.conf import settings
from django.contrib.auth.hashers import get_hashers
from django.utils.datastructures import MultiValueDict
from django.utils.functional import LazyObject, Promise
from django.views.debug import ExceptionReporter, SafeExceptionReporterFilter

# Credential fields used by sign-in, password, PIN enrollment and every signing form.
CREDENTIAL_FIELDS = frozenset(
    {
        "password",
        "password1",
        "password2",
        "current_password",
        "password_confirmation",
        "temporary_password",
        "old_password",
        "new_password1",
        "new_password2",
        "pin",
    }
)
# Stored password/PIN hashes are offline-guessing verifiers. Django's standard algorithm names are
# always recognised, so a hash made by a hasher that is no longer configured is still hidden.
STANDARD_HASH_ALGORITHMS = frozenset(
    {"argon2", "bcrypt", "bcrypt_sha256", "md5", "pbkdf2_sha1", "pbkdf2_sha256", "scrypt", "sha1"}
)
# Past these bounds a frame variable is hidden whole, so a deep, cyclic or huge structure cannot
# stall error reporting or slip through unchecked.
CLEANSE_MAX_DEPTH = 8
CLEANSE_MAX_ITEMS = 5000


@lru_cache(maxsize=8)
def _hash_pattern(algorithms):
    names = "|".join(re.escape(name) for name in sorted(algorithms, key=len, reverse=True))
    # Argon2 parameters contain commas ("m=…,t=…,p=…"); a comma and a space separate values in
    # database error text such as "Failing row contains (…)".
    return re.compile(rf"(?<![\w$])(?:{names})\$(?:[^\s'\"<>()\[\]{{}}&;,]|,(?!\s))+")


def mask_password_hashes(text, substitute=SafeExceptionReporterFilter.cleansed_substitute):
    """Replace every stored-hash token in text, wherever it appears in the string."""
    configured = frozenset(hasher.algorithm for hasher in get_hashers())
    pattern = _hash_pattern(STANDARD_HASH_ALGORITHMS | configured)
    # Unchanged text keeps its identity, so containers without a hash are reported as they are.
    return pattern.sub(substitute, text) if pattern.search(text) else text


class _CleanseLimit(Exception):
    pass


class CredentialExceptionReporterFilter(SafeExceptionReporterFilter):
    """Mask credentials and stored hashes in error reports, after Django's own masking
    (sensitive_variables/sensitive_post_parameters, settings, session cookie) in super()."""

    def get_traceback_frame_variables(self, request, tb_frame):
        variables = super().get_traceback_frame_variables(request, tb_frame)
        if not self.is_active(request):
            return variables
        return [(name, self.cleanse_credentials(name, value)) for name, value in variables]

    def cleanse_credentials(self, name, value):
        """Hide credential-named values and stored hashes at any depth; fail closed when unsure."""
        if name in CREDENTIAL_FIELDS:
            return self.cleansed_substitute
        try:
            return self._cleanse(value, CLEANSE_MAX_DEPTH, [CLEANSE_MAX_ITEMS])
        except Exception:  # Bounds exceeded, or a value that cannot be inspected safely.
            return self.cleansed_substitute

    def _cleanse_entry(self, key, value, depth, budget):
        if isinstance(key, str) and key in CREDENTIAL_FIELDS:
            return self.cleansed_substitute
        return self._cleanse(value, depth - 1, budget)

    def _cleanse(self, value, depth, budget):
        # Lazy objects are left alone: inspecting them could run queries during error reporting.
        if isinstance(value, (LazyObject, Promise)):
            return value
        if isinstance(value, str):
            return mask_password_hashes(value, self.cleansed_substitute)
        if not isinstance(value, (dict, list, tuple, set, frozenset)):
            return value
        budget[0] -= len(value)
        if depth <= 0 or budget[0] < 0:
            raise _CleanseLimit
        if isinstance(value, dict):
            pairs = list(value.lists() if isinstance(value, MultiValueDict) else value.items())
            cleansed = [(k, self._cleanse_entry(k, v, depth, budget)) for k, v in pairs]
            if all(new is old for (_, new), (_, old) in zip(cleansed, pairs, strict=True)):
                return value
            if isinstance(value, MultiValueDict):
                return MultiValueDict({k: v if isinstance(v, list) else [v] for k, v in cleansed})
            return dict(cleansed)
        items = list(value)
        cleansed = [self._cleanse(item, depth - 1, budget) for item in items]
        if all(new is old for new, old in zip(cleansed, items, strict=True)):
            return value
        if isinstance(value, list):
            return cleansed
        if isinstance(value, tuple):
            make = getattr(type(value), "_make", None)  # Named tuples keep their field names.
            return make(cleansed) if make else tuple(cleansed)
        return frozenset(cleansed) if isinstance(value, frozenset) else set(cleansed)

    def get_cleansed_multivaluedict(self, request, multivaluedict):
        cleansed = super().get_cleansed_multivaluedict(request, multivaluedict)
        hidden = [name for name in CREDENTIAL_FIELDS if name in cleansed]
        if not self.is_active(request) or not hidden:
            return cleansed
        cleansed = cleansed.copy()
        for name in hidden:
            cleansed[name] = self.cleansed_substitute
        return cleansed

    def get_post_parameters(self, request):
        parameters = super().get_post_parameters(request)
        if request is None or not self.is_active(request):
            return parameters
        hidden = [name for name in CREDENTIAL_FIELDS if name in parameters]
        if not hidden:
            return parameters
        parameters = parameters.copy()
        for name in hidden:
            parameters[name] = self.cleansed_substitute
        return parameters


class CredentialExceptionReporter(ExceptionReporter):
    """Final pass over each rendered report: hide stored hashes wherever they surface, including
    database error text ("Failing row contains …") and object representations."""

    def _mask(self, report):
        if not self.filter.is_active(self.request):
            return report
        return mask_password_hashes(report, self.filter.cleansed_substitute)

    def get_traceback_html(self):
        return self._mask(super().get_traceback_html())

    def get_traceback_text(self):
        return self._mask(super().get_traceback_text())


class CredentialLogFormatter(logging.Formatter):
    """For deployments whose LOGGING writes tracebacks: database error text can carry a stored
    hash ("Failing row contains …"), so hash tokens are hidden in every formatted record."""

    def format(self, record):
        return mask_password_hashes(super().format(record))


class ContentSecurityPolicyMiddleware:
    """Send the configured Content-Security-Policy on HTML responses that lack one."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = settings.CONTENT_SECURITY_POLICY
        if (
            policy
            and "Content-Security-Policy" not in response
            and response.get("Content-Type", "").startswith("text/html")
        ):
            response["Content-Security-Policy"] = policy
        return response
