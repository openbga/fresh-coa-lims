---
date: 2026-11-16
type: added
impact: high
title: Security keys and passkeys as a second sign-in factor
area: Account access
link: accounts:two_factor
pr: 36
---
On **Two-factor sign-in** an owner can add a named security key or passkey and use it at the second sign-in step beside, or instead of, a code from an app. Keys work only at the host name they were registered at, over HTTPS or on `localhost`.

## Technical notes

- Security keys and passkeys (Web Authentication) as a second sign-in factor. On **Two-factor sign-in** an owner adds a named key (**Add a security key or passkey**, page `/accounts/two-factor/security-key/`) after confirming the password, and a second factor once two-factor sign-in is on; the first key turns it on and shows ten recovery codes. The second sign-in step offers **Use your security key** beside the code field, and every owner change can be confirmed with a key by leaving the code empty. A refused key counts like a wrong code toward the sign-in lock and the 100-failure stop; each challenge is answered once; a signature count that does not increase is refused and logged. Keys can be removed one by one (the last one turns two-factor sign-in off, refused for a required role), and **Remove the authenticator app** keeps the keys. The administrator reset removes keys too. Keys work only at the host name they were registered at, over HTTPS or on `localhost`. New audit actions `account.security_key_added`, `account.security_key_removed`, `account.authenticator_added` and `account.authenticator_removed`.
- Security keys and passkeys: `sign_in_factors` can be `["password", "security_key"]`; account audit values gain `authenticator_app` and `security_keys` (a count). New table `accounts.SecurityKey` (migration `accounts.0008_security_keys`): public key, credential ID, signature count, host name (`rp_id`) and the owner's name for each key; no secret. New dependency `webauthn` (py_webauthn), which installs `cryptography`, `pyOpenSSL`, `cbor2`, `pyasn1` and `pyasn1-modules`. Two-factor sign-in's start buttons are now **Set up with a security key or passkey** and **Set up with an authenticator app**; for an account without an app the second step's field is labelled **Recovery code**.
