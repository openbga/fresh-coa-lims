---
title: Account action
urls: accounts:user_action
views: accounts.views.user_action
templates: accounts/form.html
models: accounts.User, auth.Group, core.PINCredential, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Authorize one identity, role or credential-lifecycle change for an existing account. The title and fields depend on the selected action; every action requires your signature and a reason.

## Who can use it

Signed-in, active users with the explicit **admin** role can open the page. An enrolled signature PIN is required before the form is available. Superuser status alone grants no web management authority. Other users receive 403; unknown accounts or action names return 404. A required password change must be completed first.

You may make permitted changes to your own account, but cannot add any role you do not already hold. No administrator can remove the admin role from, or deactivate, the last active admin-role account. Those actions can appear as links. Deactivation of the last active admin is explained before showing a form; prohibited role selections are still refused on submission.

## Layout

The action title is followed by your signing identity, **account_authorized** meaning, target account/name/roles/active state and current/resulting management revision. The form contains the action-specific fields, hidden expected revision, reason and your signing credentials. **Cancel** and the action's **Sign and …** button follow when the action is available. For a known blocker, the form is hidden and an explanation plus **Return without changes** appears instead. The target facts and your PIN-enrollment link remain visible.

## Actions

Submit buttons and editable fields below appear only when the form is available.

| Page action / submit label | Conditional fields | Effect and guard |
|---|---|---|
| Update identity / Sign and update identity | First name, Last name, Email | Updates name/contact; username stays unchanged |
| Assign roles / Sign and assign roles | Roles | Replaces the entire role set; none revokes all roles. No self-addition; preserve at least one active admin |
| Deactivate account / Sign and deactivate account | None beyond reason/signing | Disables login; already-inactive accounts and the last active admin are refused. Existing roles and history remain |
| Reactivate account / Sign and reactivate account | None beyond reason/signing | Enables login; already-active accounts are refused. Does not add roles or clear a required password change |
| Force password reset / Sign and force password reset | Optional Temporary password and confirmation | Requires a new password after sign-in. Blank keeps the current password for that sign-in; an account without a usable password requires a temporary one |
| Clear PIN lockout / Sign and clear PIN lockout | None beyond reason/signing | Clears failure count and lock deadline without changing the PIN. Requires an enrolled PIN, even if not currently locked |
| Require PIN re-enrollment / Sign and require PIN re-enrollment | None beyond reason/signing | Removes the enrolled credential; owner must enroll a new PIN. Requires an enrolled PIN; prior signatures remain |
| Enroll or change your signature PIN | Always shown | Opens your own PIN page, not the target account's enrollment |
| Cancel | Form available | Returns to the target's account record without a change |
| Return without changes | Action unavailable | Returns to the target's account record without a change |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Account / Identity / Roles / Active | `User.username`, `first_name`, `last_name`, `groups`, `is_active` | Display values | — | Confirm the target before signing; roles show None if empty |
| Reviewing / resulting revision | `User.management_revision` | Display integer | — | Signature binds current revision + 1 |
| First name / Last name | `User.first_name`, `last_name` | Text, max 150 each | Identity action | Prefilled current names; both required |
| Email | `User.email` | Email address | No | Prefilled contact on identity action; blank removes it |
| Roles | `User.groups` | Role checkboxes | No | Prefilled current roles; select every intended Admin, Analyst, Auditor, Quality or Reviewer role |
| Temporary password | `User.password` (hashed if replaced) | Masked text | Conditional | Optional initial reset credential; never displayed back or emailed |
| Confirm temporary password | — | Masked text | When temporary password supplied | Must match, otherwise Passwords do not match. |
| Revision (hidden) | `User.management_revision` | Integer | Yes | Rejects an action prepared against an outdated account |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Rationale for the selected action |
| Signing username | — | Text, max 150 | Yes | Must match your authenticated account |
| Signature PIN | `PINCredential` (verified) | Masked text | Yes | Your current signing PIN, never the target's PIN |
| Signer / meaning | `ElectronicSignature.signer_name`, `meaning` | Display text | — | Names who authorizes the change; meaning is account_authorized |

## Rules and hidden logic

Known blockers are shown before requesting a signing PIN:

| Condition | Explanation shown |
|---|---|
| You have no enrolled PIN | Enroll your signature PIN before authorizing account changes. |
| Deactivate an inactive target | This account is already inactive. |
| Deactivate the last active admin | Keep at least one active account with the admin role. |
| Reactivate an active target | This account is already active. |
| Clear lockout or require re-enrollment without a target PIN | This account has no enrolled PIN. |

If you lack your own enrolled PIN, that explanation takes precedence over a target-state blocker. These page checks do not authorize a change or replace the server's POST checks. An enrolled but locked signer PIN does not hide the form; signing still fails until that lock is resolved.

**Account changed. Reload and review before signing.** means another management change advanced the target revision. Reload and inspect the new account state before signing again. Staff and superuser flags are read-only and never changed by these forms.

Self-addition of roles returns 403: **You cannot grant yourself additional roles. Ask another administrator.** The last-active-admin guard reports **Keep at least one active account with the admin role.** Checks are serialized so concurrent changes cannot remove all active admins. Supplied temporary passwords must pass the configured password validators; blank reset requires an existing usable password.

Every successful action increments management revision and the account's session generation. Target sessions must sign in again on their next request. If you changed another account, you return to its record with **Account updated. Existing sessions must sign in again.** If you changed your own account, you are logged out with **Your account was updated. Sign in again.** A reset also redirects the target to Change password after their next login.

HTTP signing requires your typed username and PIN and a current, unrevoked session. Defaults are 15-minute idle/8-hour absolute sessions and a 15-minute signing lock after five failed PIN attempts. Denied PIN attempts remain audited. Clearing a target's PIN lock still requires a working signer PIN; this is not a way to sign through your own lockout.

The account mutation, safe before/after audit event and immutable **account_authorized** signature commit together, bound to the resulting management revision. Audit actions are **account.identity**, **account.roles**, **account.deactivate**, **account.reactivate**, **account.reset_password**, **account.unlock_pin** and **account.reenroll_pin**. Secrets and hashes are excluded from the snapshots. Validation errors return status 422 with secrets blank and safe fields preserved when the form remains available; a failed action commits no requested account change. Signer PIN-failure counters and denied-attempt audit events can still change.

## Related pages

- Account record, reached by Cancel or successful change to another account.
- [Users and roles](/accounts/users/)
- [Signature PIN](/signature-pin/)
- [Change password](/accounts/password/)
