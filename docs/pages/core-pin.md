---
title: Signature PIN
urls: core:pin
views: core.views.pin
templates: core/form.html
models: core.PINCredential, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Enrol or replace your own signature PIN, the secret you re-enter for every electronic signature.

## Who can use it

- Any signed-in user, for their own account only. No role is required to enrol; signing itself still needs the right role.

## Layout

- Title "Signature PIN", two masked fields and **Save**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save** | Always | Signed-in user | Stores the new PIN, shows "Signature PIN saved." and reloads the page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current login password | — (checked, not stored) | Masked text | Yes | Confirms it is you before the PIN changes |
| New signature PIN | `PINCredential.encoded` (hashed) | Masked, 8–32 digits | Yes | The new signing secret |

## Rules and hidden logic

- **Format**: 8 to 32 ASCII digits ("Use 8–32 digits for your signature PIN."). The form also rejects fewer than 8 characters.
- **Other refusals**: non-digit input, fewer than 8 or more than 32 digits shows "Use 8–32 digits for your signature PIN." inline.
- **Password check**: a wrong login password is refused with a 403 page ("Password confirmation failed."), not an inline error.
- **Storage**: the PIN is hashed with the standard password hasher; neither the PIN nor its hash is shown or logged. Fields are blank after any error.
- **Lock reset**: saving clears failed attempts and any temporary PIN lock.
- **Audit**: writes `pin.changed` on your account; the PIN is not in the event.

## Related pages

- Sign result review, Sign lot disposition and rule approval use this PIN.
