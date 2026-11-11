---
title: Change password
urls: accounts:password_change
views: accounts.views.password_change
templates: accounts/form.html
models: accounts.User, core.AuditEvent
reviewed: 2026-11-11
---

## Purpose

Replace your own login password, either voluntarily or because an administrator requires it. This is an audited password change, not an electronic signature or PIN change.

## Who can use it

Any signed-in active user; no laboratory role is required. Signed-out visitors must sign in. When a password change is required, other application pages redirect here until it succeeds; signing out and opening this page's help remain available.

## Layout

If required, an information message says **Choose a new password before continuing. You can sign out from the top bar.** The form contains current/new password, confirmation and reason, followed by **Change password**. **Cancel** appears only for a voluntary change. There is no signing statement or PIN field.

## Actions

| Action | Shown when | Result |
|---|---|---|
| Change password | Always | Replaces the password, clears the required-change flag, retains this session and invalidates other sessions; redirects to Material lots |
| Cancel | Password change is not required | Returns to Account access without saving |
| Sign out | Shared top bar | Ends the session, including when a required change is pending |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current password | `User.password` (verified) | Masked text | Yes | Existing login password, or the temporary password used after an administrator reset |
| New password | `User.password` (hashed) | Masked text | Yes | Must differ from the current password and pass configured validators |
| Confirm new password | — | Masked text | Yes | Must match the new password |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the password is changing |
| Required-change notice | `User.password_change_required` | Display condition | — | Explains why other application work is unavailable |

## Rules and hidden logic

Django admin’s **Change password** link redirects here. A POST to the old `/admin/password_change/` endpoint also redirects without changing credentials; enter the current/new password and reason on this form.

A wrong current password reports **Current password was not accepted.** Each wrong current password counts toward the same consecutive-failure limit as sign-in (default five); reaching it pauses password sign-in and this check for the account (default 15 minutes), and during that pause even the correct current password gets the same message. A correct password, here or at sign-in, resets the count, even when the new password is then refused. If the account's password or activation changes between that check and saving, the change is refused with the same message. Matching the old password reports **Choose a different password.** Confirmation mismatch reports **Passwords do not match.** Validators also reject passwords too similar to the account identity, too short, common or entirely numeric. Errors return status 422; password fields are blank when rerendered.

Success increments the account management revision and session generation, clears the required-change flag and writes **account.password_changed** with safe before/after values. The current session is updated to remain signed in; other sessions must sign in again on their next request. The success message is **Password changed. Other sessions have been signed out.** Normal idle and absolute session lifetimes still apply.

No PIN verification or electronic signature is created. The signature PIN, roles, activation and historical signatures are unchanged. Passwords and hashes never appear in the audit values. The redirect to Material lots does not grant a laboratory role: an account without one reaches Account access instead.

## Related pages

- [Account access](/accounts/access/)
- [Material lots](/)
- [Signature PIN](/signature-pin/)
