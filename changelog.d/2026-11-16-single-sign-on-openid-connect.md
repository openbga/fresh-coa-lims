---
date: 2026-11-16
type: added
impact: high
title: Single sign-on with the organization's identity provider
area: Account access
link: accounts:single_sign_on
pr: 40
---
Where the deployment sets it up, an owner links their account to the organization's identity provider on **Organization sign-in** and then uses **Sign in with** that provider on the sign-in page. Administrators can remove a link with a signed action.

## Technical notes

- Single sign-on with the organization's identity provider (OpenID Connect authorization code flow with PKCE), off unless `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are set; also `OIDC_PROVIDER_NAME`, `OIDC_SCOPES`, `OIDC_TOKEN_AUTH_METHOD` and `OIDC_PROMPT` (default `login`). Owners link their own account on the new page **Organization sign-in** (`accounts:single_sign_on`); the sign-in page offers **Sign in with** the provider's name (`login_sso`, `login_sso_callback`). Administrators remove a link with the signed account action `remove_single_sign_on`; **Force password reset** (`reset_password`) and two-factor resets (the account action and the `reset_two_factor` command) now also remove the account's link.
- `sign_in_factors` can be `["identity_provider"]` or `["identity_provider", <second factor>]`. Account audit values gain `single_sign_on` (the linked issuer, subject and label, or null); new audit actions `account.single_sign_on_linked`, `account.single_sign_on_unlinked` and `account.remove_single_sign_on`. New table `accounts.SingleSignOnLink` (migration `accounts.0009_single_sign_on_link`). The sign-in log gains `signin.single_sign_on_failed`. New dependencies `authlib` (with `joserfc`) and `requests` (with `urllib3`, `idna`, `charset-normalizer` and `certifi`).
