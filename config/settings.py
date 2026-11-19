import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY must be supplied (or use DEBUG=true locally).")
    SECRET_KEY = "development-only-do-not-use-in-production"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
# Render supplies this environment value; never derive trust from request headers.
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_hostname}")
INSTALLED_APPS = [
    "config.apps.AuditedAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    # Ahead of accounts, whose admin module unregisters the authenticator model (secrets).
    "django_otp",
    "django_otp.plugins.otp_totp",
    "accounts",
    "core",
    "suppliers",
    "quality",
    "catalog",
    "sampling",
    "reporting",
    "pagedocs",
    "analytical",
    "laboratory",
    "stability",
    "impact",
    "planning",
    "validation",
    "whatsnew",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "config.security.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # Outside the session, sign-in and CSRF layers, so it sees their redirects too: a redirect
    # answering the form dialog becomes an HTMX instruction (core/form_dialog.py).
    "core.form_dialog.FormDialogMiddleware",
    # Ahead of the CSRF check, which is the first code to read a submitted form.
    "core.uploads.UploadSizeMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.session_control.ControlledSessionMiddleware",
    # Re-applies each user's saved page size and sort to list views (presentation only).
    "core.preferences.GridPreferenceMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.account_navigation",
                "core.context_processors.product",
                "core.form_surfaces.form_presentation",
            ]
        },
    }
]
DATABASES = {
    "default": dj_database_url.config(
        default="postgresql://open_qual:open_qual@127.0.0.1:55433/open_qual",
        conn_max_age=60,
        conn_health_checks=True,
    )
}
if test_database_name := os.environ.get("TEST_DATABASE_NAME"):
    if (
        not test_database_name.startswith("test_")
        or test_database_name == DATABASES["default"]["NAME"]
    ):
        raise RuntimeError("TEST_DATABASE_NAME must name a separate test_ database.")
    DATABASES["default"]["TEST"] = {"NAME": test_database_name}
AUTH_USER_MODEL = "accounts.User"
# Only the throttled backend: a second backend would accept credentials refused during a lock.
AUTHENTICATION_BACKENDS = ["accounts.authentication.ThrottledModelBackend"]
LOGIN_FAILURE_LIMIT = int(os.environ.get("LOGIN_FAILURE_LIMIT", "5"))
LOGIN_LOCK_SECONDS = int(os.environ.get("LOGIN_LOCK_SECONDS", "900"))
if LOGIN_FAILURE_LIMIT < 1 or LOGIN_LOCK_SECONDS < 60:
    raise RuntimeError("Sign-in throttling needs LOGIN_FAILURE_LIMIT >= 1, LOCK_SECONDS >= 60.")
# Two-factor sign-in (accounts.two_factor). Members of these laboratory roles must set up an
# authenticator app before they can use the workspace: a comma-separated list of roles, "all"
# for every account, or empty for none (each account may still set it up). Shared demonstration
# accounts, whose credentials are published, cannot set it up and are not required to.
MFA_REQUIRED_ROLES = frozenset(
    role.strip().lower()
    for role in os.environ.get("MFA_REQUIRED_ROLES", "").split(",")
    if role.strip()
)
if not MFA_REQUIRED_ROLES <= {"all", "admin", "analyst", "auditor", "quality", "reviewer"}:
    raise RuntimeError(
        "MFA_REQUIRED_ROLES must list laboratory roles (admin, analyst, auditor, quality, "
        "reviewer) or be all."
    )
# Seconds allowed between an accepted password and the authenticator code.
MFA_PENDING_SECONDS = 300
# Sign-in with a security key or passkey alone, without the password (accounts.views.
# login_passkey). The key must verify its holder with its own PIN, fingerprint or face. Set to
# false to ask every account for its password first.
PASSKEY_SIGN_IN = os.environ.get("PASSKEY_SIGN_IN", "true").lower() == "true"
# Single sign-on with the organization's identity provider (OpenID Connect, accounts.
# single_sign_on). Off unless the issuer, client ID and client secret are all set. Only accounts
# whose owner linked an account at the provider sign in this way; none are created from it.
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").strip()
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
# The name on the sign-in button: "Sign in with <name>".
OIDC_PROVIDER_NAME = os.environ.get("OIDC_PROVIDER_NAME", "").strip() or "your organization"
OIDC_SCOPES = os.environ.get("OIDC_SCOPES", "openid email profile").split()
# How the client authenticates to the token endpoint: client_secret_basic or client_secret_post.
OIDC_TOKEN_AUTH_METHOD = os.environ.get("OIDC_TOKEN_AUTH_METHOD", "client_secret_basic").strip()
# Sent as the prompt parameter. "login" asks the provider to authenticate the person at every
# sign-in, so that a session someone else left open at the provider is not used; empty leaves
# it to the provider.
OIDC_PROMPT = os.environ.get("OIDC_PROMPT", "login").strip()
OIDC_TIMEOUT_SECONDS = 10
SINGLE_SIGN_ON = bool(OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET)
if SINGLE_SIGN_ON:
    from urllib.parse import urlsplit

    _issuer = urlsplit(OIDC_ISSUER)
    if not (
        _issuer.scheme == "https"
        or (_issuer.scheme == "http" and _issuer.hostname in {"localhost", "127.0.0.1"})
    ) or (_issuer.query or _issuer.fragment):
        raise RuntimeError(
            "OIDC_ISSUER must be an https URL without query or fragment (http only on localhost)."
        )
    if "openid" not in OIDC_SCOPES:
        raise RuntimeError("OIDC_SCOPES must include openid.")
    if OIDC_TOKEN_AUTH_METHOD not in {"client_secret_basic", "client_secret_post"}:
        raise RuntimeError(
            "OIDC_TOKEN_AUTH_METHOD must be client_secret_basic or client_secret_post."
        )
elif OIDC_ISSUER or OIDC_CLIENT_ID or OIDC_CLIENT_SECRET:
    raise RuntimeError("Single sign-on needs OIDC_ISSUER, OIDC_CLIENT_ID and OIDC_CLIENT_SECRET.")
OTP_TOTP_ISSUER = "OpenBGA QM LIMS"
# Failed codes count toward the account's sign-in failure limit and lock (LOGIN_FAILURE_LIMIT),
# like a wrong password, so the library's own per-device delay is switched off.
OTP_TOTP_THROTTLE_FACTOR = 0
OTP_ADMIN_HIDE_SENSITIVE_DATA = True
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Sign-in events go to standard output so they survive database resets (accounts.signin_log).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"masked": {"()": "config.security.CredentialLogFormatter"}},
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "masked",
        }
    },
    "loggers": {"openbga.signin": {"handlers": ["stdout"], "level": "INFO", "propagate": False}},
}
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.dummy.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.invalid")
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# One year once HTTPS is confirmed; subdomain/preload scope is an explicit operator choice.
SECURE_HSTS_SECONDS = 0 if DEBUG else int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.environ.get("SECURE_HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"
)
SECURE_HSTS_PRELOAD = os.environ.get("SECURE_HSTS_PRELOAD", "false").lower() == "true"
X_FRAME_OPTIONS = "DENY"
# Vendored assets only: no inline script/style, eval, external origins or framing.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
DEFAULT_EXCEPTION_REPORTER = "config.security.CredentialExceptionReporter"
DEFAULT_EXCEPTION_REPORTER_FILTER = "config.security.CredentialExceptionReporterFilter"
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
# core.uploads.UploadSizeMiddleware refuses an upload that declares too large a body before it
# is read; the first handler stops a file that exceeds RAW_DATA_MAX_BYTES while it is received.
FILE_UPLOAD_HANDLERS = [
    "core.uploads.BoundedUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# AGPL-3.0 section 13: link users to the source of the running version. Point this at your own
# repository when you deploy a modified version.
SOURCE_CODE_URL = os.environ.get("SOURCE_CODE_URL", "https://github.com/openbga/qm-lims")

REPORT_SYNTHETIC_DATA_NOTICE = (
    os.environ.get("REPORT_SYNTHETIC_DATA_NOTICE", "true").lower() == "true"
)
# The certificate check without an account (reporting.checks, /check/): a recipient submits a
# certificate file, or its SHA-256, and learns whether the laboratory issued it and whether it
# is current. Off unless the laboratory offers it; the signed-in check is always available.
CERTIFICATE_CHECK = os.environ.get("CERTIFICATE_CHECK", "false").lower() == "true"
# Checks without an account accepted per minute, all recipients together.
CERTIFICATE_CHECK_RATE = int(os.environ.get("CERTIFICATE_CHECK_RATE", "20"))
if not 1 <= CERTIFICATE_CHECK_RATE <= 600:
    raise RuntimeError("CERTIFICATE_CHECK_RATE must be from 1 to 600 checks a minute.")

# Product defaults; deployers validate these against their controlled-access procedures.
SESSION_IDLE_SECONDS = int(os.environ.get("SESSION_IDLE_SECONDS", "900"))
SESSION_ABSOLUTE_SECONDS = int(os.environ.get("SESSION_ABSOLUTE_SECONDS", "28800"))
if not 60 <= SESSION_IDLE_SECONDS <= SESSION_ABSOLUTE_SECONDS:
    raise RuntimeError("Session limits must satisfy 60 <= idle <= absolute.")
SESSION_COOKIE_AGE = SESSION_ABSOLUTE_SECONDS
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

FORMS_URLFIELD_ASSUME_HTTPS = True

ANALYTICAL_REQUIREMENT_PROVIDER = "config.integrations.CatalogRequirementProvider"
# Result entry asks the laboratory module whether the analyst is qualified for the method and
# whether each selected instrument and reagent or standard lot is fit for use. Without this
# setting results are held.
ANALYTICAL_BENCH = "config.integrations.LaboratoryBench"
# The testing gate asks the lot record which supplier certificate results were accepted in place
# of a test. Without this setting no supplier result answers a requirement.
ANALYTICAL_SUPPLIER_RESULTS = "config.integrations.AcceptedSupplierResults"
# A test belongs to the testing of a lot or to a stability pull. For a pull's tests the testing
# module asks the stability module for the acceptance criteria of the protocol, whether the pull
# still takes testing, and for the lock every evidence change takes. Without this setting no
# pull is tested in the system.
ANALYTICAL_STABILITY_PULLS = "config.integrations.StabilityPulls"
# Or to the reassessment of a released lot: the testing module asks the lot record for the
# requirements in force, whether the reassessment still takes testing, and for its lock. Without
# this setting no reassessment is tested in the system.
ANALYTICAL_REASSESSMENTS = "config.integrations.Reassessments"
# Reviewing or returning a test asks the laboratory module whether the reviewer holds a current
# qualification to review the method, where the test's approved method version asks for one.
# The system check analytical.E001 refuses to start without it.
ANALYTICAL_REVIEWERS = "config.integrations.LaboratoryReviewers"
# Replacing a lot's requirements during testing asks the testing module which of the lot's tests
# carry over and which are superseded. Without this setting requirements cannot be replaced
# once testing has started.
REQUIREMENT_REPLACEMENT_TESTING = "config.integrations.TestingUnderReplacement"
# Raw-data files are stored in PostgreSQL with their test. This is the largest file accepted,
# in bytes; each upload is held in memory while its checksum is calculated.
RAW_DATA_MAX_BYTES = int(os.environ.get("RAW_DATA_MAX_BYTES", str(10 * 1024 * 1024)))
if not 1 <= RAW_DATA_MAX_BYTES <= 50 * 1024 * 1024:
    raise RuntimeError("RAW_DATA_MAX_BYTES must be from 1 to 52428800 (50 MiB).")
# Optional ceiling on all stored files of the deployment together (raw-data files of tests and
# evidence files of rehearsals), in bytes; 0 sets none.
RAW_DATA_TOTAL_MAX_BYTES = int(os.environ.get("RAW_DATA_TOTAL_MAX_BYTES", "0"))
if RAW_DATA_TOTAL_MAX_BYTES < 0:
    raise RuntimeError("RAW_DATA_TOTAL_MAX_BYTES must be 0 (no ceiling) or a positive size.")
