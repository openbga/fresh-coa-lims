---
date: 2026-11-16
type: added
impact: high
title: Two-factor sign-in with an authenticator app and recovery codes
area: Account access
link: accounts:two_factor
pr: 34
---
An owner can set up an authenticator app on **Two-factor sign-in** and then signs in with the password and a current code. Ten one-time recovery codes are shown once, and wrong codes count toward the account's sign-in lock.

## Technical notes

- Two-factor sign-in. **Two-factor sign-in** (`/accounts/two-factor/`, linked from Account access) sets up an authenticator app: confirm the password, scan the QR code or type the key, and confirm with a code from the app; ten one-time recovery codes are then shown once. An account with an authenticator signs in in two steps: the password, then a current code or an unused recovery code on `/accounts/login/verify/` within five minutes (`MFA_PENDING_SECONDS`). Each code from the app works once; wrong codes count toward the account's sign-in failure limit and lock (`LOGIN_FAILURE_LIMIT`, `LOGIN_LOCK_SECONDS`), and 100 consecutive wrong codes stop the second factor until an administrator resets it. New recovery codes, a new app or turning it off need the password and a current code.
- New audit actions: `account.two_factor_enabled`, `account.two_factor_replaced`, `account.two_factor_disabled`, `account.two_factor_stopped`, `account.recovery_codes_replaced`, `account.recovery_code_used` and `account.reset_two_factor`. The sign-in log adds `signin.second_factor_requested` and `signin.second_factor_failed`.
- The `authentication_context` of a web signature gains `sign_in_factors`: `["password"]`, `["password", "totp"]` or `["password", "recovery_code"]`, as the signer's session signed in. Account audit values (`before`/`after` of `account.*` events) gain `two_factor`, `two_factor_stopped` and `recovery_codes_left`. `LoginThrottle` gains `code_failures`.
- New dependencies: `django-otp` (time-based codes and the authenticator model, apps `django_otp` and `django_otp.plugins.otp_totp`) and `segno` (the QR code). The library's per-device delay is off (`OTP_TOTP_THROTTLE_FACTOR = 0`): failed codes count toward the account's own sign-in lock instead. Its admin page for authenticators is not registered.
- `accounts.authentication.confirm_password` takes `reset=False` to leave the failure count alone after a correct password, for a check that continues with a second factor; for an account with two-factor sign-in it never resets the count, so changing the password or the PIN cannot clear failures between guessed codes.
