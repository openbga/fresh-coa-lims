---
title: Account access
urls: accounts:access
views: accounts.views.access
templates: accounts/access.html
models: accounts.User
reviewed: 2026-11-10
---

## Purpose

See your laboratory roles and the next step if access is missing. Account administrators can reach signed user management or deployment-operator guidance here.

## Who can use it

Any signed-in user, including an account with no laboratory role. A required password change takes precedence and redirects to Change password. The management guidance appears for an active superuser or an active user with the explicit **admin** role; only the latter can use web user management. Superuser status alone grants no laboratory or web account-management role.

## Layout

The heading is **No laboratory role assigned** when none is present, otherwise **Account access**. The page shows your username, assigned roles or access-request guidance, and **Change password**. Administrators also see **Account and role management**, applicable management links and command guidance.

## Actions

| Action | Shown when | Result |
|---|---|---|
| Open workspace | At least one recognized laboratory role | Opens Material lots; later actions still check their own permissions |
| Change password | Always | Opens your password-change form |
| Manage users and roles | Explicit admin role | Opens Users and roles |
| View accounts in Django admin | Account administrator with staff status and user view/change permission | Opens the read-only Django account list |
| Sign out | Shared top bar | Ends this session and returns to sign-in |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signed-in username | `User.username` | Text | — | Give this identifier to the administrator when requesting access |
| Assigned laboratory roles | `User.groups` | Sorted recognized names | — | admin, analyst, auditor, quality or reviewer; unrelated groups do not grant laboratory access |
| Account-administrator guidance | `User.is_active`, `is_superuser`, `groups` | Conditional section | — | Distinguishes operator/bootstrap capability from explicit web management authority |
| Django account link | `User.is_staff`, user permissions | Conditional link | — | Existing staff/user permissions are required; this page grants none |
| Bootstrap command | `User.username` | Shell-quoted text | — | Displayed to a roleless account administrator for operator-assisted initial setup |

## Rules and hidden logic

Opening this GET-only page changes no roles or scientific records. Workspace entry without a recognized role redirects here; denied deep links still return 403 with access guidance.

Web account changes require the **admin** role, a reason, and fresh signing username/PIN. Administrators cannot grant themselves additional roles or remove/deactivate the last active admin. Scientific approval still requires its designated role and independence; admin does not grant Django staff access.

The operator's `assign_roles` command replaces the complete role set. Include every intended role; none revokes all laboratory roles, subject to self-addition and last-admin safeguards. The displayed bootstrap command is valid only for the initial roleless superuser when no active admin-role account exists. It is guidance, not a button that runs the command.

## Related pages

- [Material lots](/)
- [Users and roles](/accounts/users/)
- [Change password](/accounts/password/)
- [Read-only Django account administration](/admin/accounts/user/)
