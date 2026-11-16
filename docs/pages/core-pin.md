---
title: Signature PIN
urls: core:pin
views: core.views.pin
templates: core/form.html
models: core.PINCredential, core.AuditEvent
reviewed: 2026-11-12
---

## Purpose

Enrol or replace your own signature PIN, the secret you re-enter for every electronic signature.

## Who can use it

- Any signed-in user, for their own account only. No role is required to enrol; signing itself still needs the right role. If password replacement is required, complete Change password first.
- A shared demonstration account, whose PIN is published in the sign-in announcement, cannot enrol or replace it.

## Layout

- Title "Signature PIN", two masked fields and **Save**.
- For a shared demonstration account: the title and an explanation, without fields.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save** | Not a shared demonstration account | Signed-in user | Stores the new PIN, shows "Signature PIN saved." and reloads the page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current login password | — (checked, not stored) | Masked text | Yes | Confirms it is you before the PIN changes |
| New signature PIN | `PINCredential.encoded` (hashed) | Masked, 8–32 digits | Yes | The new signing secret |

## Rules and hidden logic

- **Format**: 8 to 32 ASCII digits ("Use 8–32 digits for your signature PIN."). The form also rejects fewer than 8 characters.
- **Other refusals**: non-digit input, fewer than 8 or more than 32 digits shows "Use 8–32 digits for your signature PIN." inline.
- **Password check**: a wrong login password is refused with a 403 page ("Password confirmation failed."), not an inline error. Each wrong password counts toward the same consecutive-failure limit as sign-in (default five); reaching it pauses password sign-in and this confirmation for the account (default 15 minutes), and during that pause even the correct password gets the same refusal. A correct password, here or at sign-in, resets the count, even if saving the PIN then fails. If the account's password or activation changes between that check and saving, the PIN is not saved and the same refusal appears.
- **Shared demonstration account**: the demonstration seed marks the accounts it publishes in the sign-in announcement. Such an account sees "This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here." instead of the form; a POST returns status 403 and the PIN is unchanged. An admin's **Force password reset** or **Require PIN re-enrollment** ends this for the account.
- **Storage**: the PIN is hashed with the standard password hasher; neither the PIN nor its hash is shown or logged. Fields are blank after any error.
- **Lock reset**: saving clears failed attempts and any temporary PIN lock.
- **Administrative recovery**: an admin may clear your signing lock or require re-enrollment with a signed, reasoned account action. Re-enrollment removes the prior credential and invalidates earlier sessions; enroll here after signing in again. Old signatures remain intact.
- **Audit**: writes `pin.changed` on your account; the PIN is not in the event.

## Related pages

- Sign result review, Sign lot disposition, rule approval and signed account administration use this PIN.
- [Account access](/accounts/access/)
- [Change password](/accounts/password/)
