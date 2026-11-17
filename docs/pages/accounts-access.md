---
title: Account access
urls: accounts:access
views: accounts.views.access
templates: accounts/access.html
models: accounts.User
reviewed: 2026-11-17
summary: Your laboratory roles, links to your own sign-in settings, and the next step when you have no role yet. Account administrators also see how roles are managed.
---

## Common tasks
### Open your work
1. Select [[Open workspace]]. It shows only when you hold at least one laboratory role, and opens the dashboard.
### Change your sign-in settings
1. Select [[Password]] to see your login password's state and change it.
2. Select [[Two-factor sign-in]] to add a security key, passkey or authenticator app.
3. Select [[Organization sign-in]] to link your organization account. It shows only when single sign-on is set up.
### Ask for a laboratory role
1. If the page says your account has no laboratory role, give your username to your organization's account administrator.
2. Select [[Sign out]] in the top bar while access is arranged.
### Manage users and roles
1. With the admin role, select [[Manage users and roles]] to open the account list.
## Good to know
- Signing in, or holding superuser status, does not grant laboratory access. Only an assigned laboratory role does.
- The admin role permits account administration and read access. It does not grant scientific approval authority.
- Each action still requires its designated role, and independent review where it applies. A menu link only means you can read that area.
- Administrators cannot grant themselves additional roles or remove the last active admin.
- This page changes nothing. The command shown to administrators is guidance for the deployment operator, not a button.

## Purpose

See your laboratory roles and the next step if access is missing. Account administrators can reach signed user management or deployment-operator guidance here.

## Who can use it

Any signed-in user, including an account with no laboratory role. A required password change takes precedence and redirects to Change password. The management guidance appears for an active superuser or an active user with the explicit **admin** role; only the latter can use web user management. Superuser status alone grants no laboratory or web account-management role.

## Layout

The heading is **No laboratory role assigned** when none is present, otherwise **Account access**. With a role, the **Assigned laboratory roles** card shows your username, your roles and **Open workspace**; without one, a "No role" notice gives your username and the access-request guidance. The **Sign-in** card links **Change password**, **Two-factor sign-in** and, when the deployment configures single sign-on, **Organization sign-in**. Administrators also see the **Account and role management** card: the read-only Django admin link (bootstrap administrators), the **Manage users and roles** button (admin role) and the command guidance.

The shared menu shows destinations your assigned roles can open. All five roles can read the laboratory areas under **Work**, **Configuration** and **Records**. **Audit trail** appears only for admin, quality or auditor; **Users and roles** and **Sign-in announcement** appear only for admin. Without a recognized role, only the **Account** section remains, with **Signature PIN** and **Account access**. No empty laboratory sections are shown.

## Actions

| Action | Shown when | Result |
|---|---|---|
| Open workspace | At least one recognized laboratory role | Opens the Dashboard; later actions still check their own permissions |
| Password | Always | Opens Password, where you change your password |
| Manage users and roles | Explicit admin role | Opens Users and roles |
| View accounts in Django admin | Account administrator with staff status and user view/change permission | Opens the read-only Django account list |
| Two-factor sign-in | Always | Opens your own two-factor sign-in settings |
| Organization sign-in | The deployment configures single sign-on | Opens your link to the organization's identity provider |
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

Menu access combines all your assigned roles and is checked on each page load. Staff or superuser status alone adds no laboratory menu links. Menu visibility reflects read access; creating, changing and signing records still require the designated role and applicable record conditions.

Web account changes require the **admin** role, a reason, and fresh signing username/PIN. Administrators cannot grant themselves additional roles or remove/deactivate the last active admin. Scientific approval still requires its designated role and independence; admin does not grant Django staff access.

The operator's `assign_roles` command replaces the complete role set. Include every intended role; none revokes all laboratory roles, subject to self-addition and last-admin safeguards. The displayed bootstrap command is valid only for the initial roleless superuser when no active admin-role account exists. It is guidance, not a button that runs the command.

## Related pages

- [Dashboard](/)
- [Users and roles](/accounts/users/)
- [Password](/accounts/password/)
- [Two-factor sign-in](/accounts/two-factor/)
- [Organization sign-in](/accounts/single-sign-on/), when configured.
- [Read-only Django account administration](/admin/accounts/user/)
