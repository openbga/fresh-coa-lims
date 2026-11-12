# Security policy

## Supported versions

OpenBGA Fresh CoA LIMS is pre-1.0 (see `version` in `pyproject.toml`). Only the latest commit on `main` receives security fixes. There are no maintained release branches.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub private vulnerability reporting: open the repository **Security** tab, choose **Report a vulnerability**, or go to <https://github.com/openbga/fresh-coa-lims/security/advisories/new>.

Do not open a public issue, pull request or discussion for a vulnerability, and do not post details elsewhere before a fix is available.

Please include:

- the affected commit or version and how it is deployed (local development, container, hosting service);
- what an attacker can do and what access they need (anonymous, signed-in user, a specific role, administrator);
- numbered steps or a minimal proof of concept that reproduces the problem;
- any logs or output, with secrets removed.

Use synthetic data only. Never attach real laboratory, customer or personal data, real credentials, PINs or database dumps to a report. If you came across such data while testing a deployment, do not copy it; tell the deployment's operator.

## Scope

In scope: this repository's source code, its default configuration, the container image built from its `Dockerfile` and the migrations. Examples of issues we want to hear about:

- bypass of authentication, session limits, role checks or the independent-review rule;
- signing without a fresh username and PIN, PIN or password disclosure, or lockout bypass;
- changing or deleting signed records, audit history or issued reports;
- injection, cross-site scripting, request forgery, unsafe file or PDF handling, server-side request forgery;
- exposure of secrets, hashes or other users' data.

Out of scope: weaknesses that exist only in a deployment you operate (your hosting account, network, backups, identity proofing and operating procedures), the `DEBUG` development fallbacks when `DEBUG` is enabled on a public instance (the documentation says never to do this), denial of service by volume, missing hardening headers without a demonstrated impact, and vulnerabilities in third-party dependencies that are not reachable through this project (report those upstream).

## What to expect

This is a community project and reports are handled on a best-effort basis. There is no committed response or fix timeline. We will try to confirm the report, fix it on `main` and publish a GitHub security advisory crediting the reporter, unless you prefer to remain anonymous.

## Coordinated disclosure

Please allow time for a fix before publishing details. We will agree a disclosure date with you in the advisory thread once the fix is ready. If you do not hear back, you may follow normal coordinated-disclosure practice for your situation.

## Deploying safely

Running this software safely is the responsibility of whoever deploys it. Read [docs/operations.md](docs/operations.md) and the deployment section of the [README](README.md#deployment) before exposing an instance. At minimum: use a unique `SECRET_KEY`, never enable `DEBUG` on a public instance, serve over HTTPS with correct hosts and trusted origins, do not seed demonstration data, and keep backups encrypted and restricted.

OpenBGA Fresh CoA LIMS makes no claim of regulatory compliance or validation. See the README for the stated limits.

## Hardening checklist

Check these before exposing an instance. They describe software settings, not a complete security programme.

1. Leave `DEBUG` unset or `false`. The application refuses to start without `SECRET_KEY` when `DEBUG` is off.
2. Set a unique random `SECRET_KEY` from a secret store. Rotating it signs everyone out.
3. Set `ALLOWED_HOSTS` to the exact host names and `CSRF_TRUSTED_ORIGINS` to the exact `https://` origins.
4. Serve only over HTTPS through a reverse proxy that overwrites `X-Forwarded-Proto`; the application trusts that header. Never expose the application port directly.
5. HSTS defaults to one year when `DEBUG` is off. Lower `SECURE_HSTS_SECONDS` while first verifying HTTPS. Enable `SECURE_HSTS_INCLUDE_SUBDOMAINS` or `SECURE_HSTS_PRELOAD` only if every subdomain is HTTPS-only.
6. Sessions use secure, HttpOnly cookies, end at browser close and expire after 15 minutes idle or 8 hours (`SESSION_IDLE_SECONDS`, `SESSION_ABSOLUTE_SECONDS`).
7. Password sign-in locks an account for 15 minutes after 5 consecutive failures (`LOGIN_FAILURE_LIMIT`, `LOGIN_LOCK_SECONDS`); signature PINs lock in the same way. Anyone who knows a username can trigger a lock, so add per-address rate limiting at the proxy and review repeated locks.
8. Responses carry a same-origin Content-Security-Policy, `X-Frame-Options: DENY` and `nosniff`. Update the policy before adding any external script, style, font or analytics.
9. `/admin/` is a read-only view of account records for staff users and grants no laboratory authority. Keep staff and superuser accounts to a minimum, or block `/admin/` at the proxy if you do not use it.
10. Create the first administrator with `createsuperuser` and `assign_roles`, add people with `create_staff` or **Users and roles**, and have each person set their own password and PIN. Never run `seed_demo` or set `DEMO_PASSWORD`/`DEMO_PIN` on a real instance. The sign-in announcement is readable by anyone who can reach the sign-in page: never put credentials of real accounts in it.
11. Use separate database roles for migrations and runtime. The append-only triggers stop ordinary application writes, not a database owner. Keep the database on a private network and keep backups encrypted, access-restricted and restore-tested.
12. Credential fields are masked in Django error reports. Configure any additional error tracker not to capture request bodies.
13. `/health/` and `/ready/` are unauthenticated and return only a status word.
14. Set `SOURCE_CODE_URL` to the source of the version you run (AGPL-3.0 section 13).
15. Run `python manage.py check --deploy` with the production environment and review every warning.
