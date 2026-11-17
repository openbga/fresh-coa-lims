---
date: 2026-11-17
type: changed
impact: high
title: Every form opens in a dialog over the record, signing included
area: Whole application
---
Adding a sample, recording a pull or a result, correcting a receipt, creating an account and every other form now opens in a dialog over the page it was opened from, with the page dimmed behind it. Signing forms open the same way on the signature card: the signing username and PIN are entered every time, a refused PIN is cleared, and nothing about who may sign or what a signature binds has changed. **Signature PIN** shows its state, and **Change signature PIN** opens the change in a dialog. Security keys and passkeys register inside the dialog too. Opening a form's address directly shows it over its record or list, and every signature asks for the reason, then the signing username and PIN, in that order.

## Technical notes

- `core/form_surfaces.py` registers every form route with its dialog size and roles; `tests/test_form_dialog.py` fails when a form route is neither registered nor listed as a page with its reason (the two sign-in steps, the two-factor overview and a required password change, which has no Cancel).
- Signing in the dialog keeps the server checks: a refused PIN answers 422 with the PIN cleared and the attempt counted, a stale revision is refused, and success answers 204 with `HX-Redirect` to the record.
- New URL names `core:pin_status` (`/signature-pin/`); the change form `core:pin` moved to `/signature-pin/change/`.
- Every date-time field uses the shared date-time control at minute precision.
