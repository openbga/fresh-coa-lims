---
title: Account record
urls: accounts:user_detail
views: accounts.views.user_detail
templates: accounts/user.html, includes/history_item.html
models: accounts.User, core.PINCredential, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Inspect one account's identity, roles, security state and history before authorizing a change. The page heading is the username.

## Who can use it

Signed-in, active users with the explicit **admin** role; other users receive 403. Superuser status alone is insufficient. An unknown account returns 404 after the role check. A required password change must be completed first.

## Layout

The **Users and roles** breadcrumb precedes account facts and the action links. **Account history** shows newest events with recorded values and any signature manifestation. There are 30 events per page; an empty history says **No account events recorded.**

## Actions

| Action | Shown when | Result |
|---|---|---|
| Users and roles | Always | Returns to the account list |
| Update identity | Always | Opens name/email correction |
| Assign roles | Always | Opens replacement of the complete role set |
| Deactivate account / Reactivate account | Active / inactive account respectively | Opens the corresponding signed status change |
| Force password reset | Always | Opens required password replacement, optionally with a temporary password |
| Clear PIN lockout | A PIN credential exists | Opens clearing of failure count and lock time; a current lock is not required |
| Require PIN re-enrollment | A PIN credential exists | Opens revocation of the enrolled PIN |
| Inspect recorded values | Each history event | Expands preserved Before/After values |
| Previous / Next | An adjacent history page exists | Moves through account history |

Visible actions still enforce their rules on submission, including no self-addition of roles and last-active-admin protection.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Username (heading) | `User.username` | Text | — | Stable login identifier; not editable here |
| Identity / Email | `User.first_name`, `last_name`, `email` | Text | — | Current name/contact; absent values show Not supplied |
| Roles | `User.groups` | Sorted names | — | Current access groups, or No role assigned |
| Status | `User.is_active` | Active/Inactive | — | Whether login is permitted |
| Last sign-in | `User.last_login` | Date/time and zone | — | Last login, or Never signed in |
| Password change required | `User.password_change_required` | Yes/No | — | Whether the user must replace their password before continuing |
| Signature PIN | `PINCredential.user`, `locked_until`, `failures` | Enrollment, timestamp, count | — | Enrollment required/Enrolled, stored lock deadline when present and failure count; no PIN/hash is displayed |
| Management revision | `User.management_revision` | Integer | — | Revision checked by signed account-change forms |
| Django staff / superuser | `User.is_staff`, `is_superuser` | Yes/No | — | Read-only flags; these actions never change them |
| History action / time / actor / reason | `AuditEvent.action`, `occurred_at`, `actor`, `reason` | Text/date-time | — | Attribution and rationale for the event |
| Before / After | `AuditEvent.before`, `after` | Structured values | — | Preserved safe account snapshots; no credential hashes |
| Signed by / meaning / time / revision | `ElectronicSignature.signer_name`, `meaning`, `signed_at`, `revision` | Text/date-time/integer | — | Displayed when the event has a signature |
| History page (`page`) | — | Integer | No | Defaults to page 1; 30 events per page |

## Rules and hidden logic

History contains events for this account, ordered by time descending then event ID descending. Non-numeric pages select page 1; out-of-range pages select the last page. Not every event is signed: self-service password changes are audited without an electronic signature.

Signed administration preserves an account snapshot and signature with meaning **account_authorized**. Every administrative account change advances the management revision and invalidates existing target sessions. The next request requires sign-in again; changing your own account logs you out immediately after success. Clearing PIN lockout does not change the PIN. Re-enrollment removes the credential but preserves prior signatures/history.

## Related pages

- [Users and roles](/accounts/users/)
- Account action form, reached through the links above.
- [Signature PIN](/signature-pin/)
