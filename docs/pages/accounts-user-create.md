---
title: Create account
urls: accounts:user_create
views: accounts.views.user_create
templates: accounts/form.html
models: accounts.User, auth.Group, core.PINCredential, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Create a named account with an initial password and explicit laboratory roles. Your signature authorizes creation; the new user must replace the initial password at first sign-in.

## Who can use it

Signed-in, active users with the explicit **admin** role and a current session can open the page. Their own enrolled signing PIN is required before the form is available. Superuser status alone is insufficient. Other roles receive 403. Complete any required password change before using this page.

## Layout

A signing statement identifies you and the meaning **account_authorized**. It explains revision 1, mandatory first password change and the account safeguards. With an enrolled PIN, the form shows identity, roles, initial password, reason and signing credentials, followed by **Cancel** and **Sign and create account**. Without one, the form is hidden and the page says **Enroll your signature PIN before authorizing account changes.** The enrollment link remains available, alongside **Return without changes**.

## Actions

| Action | Shown when | Result |
|---|---|---|
| Enroll or change your signature PIN | Always | Opens your own PIN enrollment page; this does not enroll the new user's PIN |
| Sign and create account | Your PIN is enrolled | Creates the account and signature, then opens its record with a reminder to share the initial password privately |
| Cancel | The form is available | Returns to Users and roles without creating an account |
| Return without changes | Your PIN is not enrolled | Returns to Users and roles without creating an account |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Username | `User.username` | Text, max 150 | Yes | Unique login identifier; letters, digits and permitted username characters (`@`, `.`, `+`, `-`, `_`) |
| First name / Last name | `User.first_name`, `last_name` | Text, max 150 each | Yes | Identifies the individual account holder |
| Email | `User.email` | Email address | No | Contact value; this page does not verify it or send an invitation |
| Roles | `User.groups` | Admin, Analyst, Auditor, Quality, Reviewer checkboxes | No | Initial complete role set; none creates an account without laboratory access |
| Initial password | `User.password` (hashed) | Masked text | Yes | Initial login secret, checked against configured password validators |
| Confirm initial password | — | Masked text | Yes | Must match the initial password |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why this account/access is authorized |
| Signing username | — | Text, max 150 | Yes | Your current username, not the new user's username |
| Signature PIN | `PINCredential` (verified) | Masked text | Yes | Your current PIN, re-entered to authorize creation |
| Signer / meaning | `ElectronicSignature.signer_name`, `meaning` | Display text | — | Your identity and account_authorized |
| Starting revision | `User.management_revision` | Display integer | — | New account starts at revision 1 |

## Rules and hidden logic

The username must be valid and unused. Password confirmation mismatch shows **Passwords do not match.** Configured validators reject passwords too similar to identity, too short, common or entirely numeric. Passwords and PINs are never copied into history or signature content; they are cleared when the form rerenders after an error.

The account starts active, without staff/superuser flags or an enrolled PIN. It must change its password before accessing the workspace, management or PIN enrollment. Share the initial password through an approved private channel; this page sends no email.

The enrollment check explains the blocker before requesting credentials; it does not replace server-side POST validation. You must type your own signing username and PIN. Five failed PIN attempts cause a 15-minute lock; failed attempts remain audited even though creation fails. Idle/absolute session defaults are 15 minutes/8 hours. A stale/revoked session or required password change prevents signing.

Creation, assigned roles, the **account.created** audit event and immutable **account_authorized** signature commit together. The signature binds the new account's revision and safe snapshot. Validation errors return status 422 with safe input preserved when the form remains available; failure creates no account. Administrative authority does not grant scientific approval or allow self-review.

## Related pages

- [Users and roles](/accounts/users/)
- Account record, opened after creation.
- [Signature PIN](/signature-pin/)
- [Change password](/accounts/password/)
