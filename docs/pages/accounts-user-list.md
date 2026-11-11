---
title: Users and roles
urls: accounts:user_list
views: accounts.views.user_list
templates: accounts/users.html
models: accounts.User, auth.Group
reviewed: 2026-11-10
---

## Purpose

Find an individual account, inspect its access and open a signed account-management action.

## Who can use it

Signed-in, active users with the explicit **admin** role. Others receive 403, including superusers without that role. A pending required password change redirects to Change password before management can continue.

## Layout

The header has **Create account**. A filter card is followed by the matching-account count, a table with Account, Identity, Roles, Status and Last sign-in, then paging. Empty text distinguishes **No accounts found.** from **No accounts match these filters. Clear or adjust them.**

## Actions

| Action | Shown when | Result |
|---|---|---|
| Create account | Always | Opens signed account creation |
| Filter | Always | Applies all entered filters and returns to page 1 |
| Clear filters | Always | Restores the unfiltered list |
| Account username | Each row | Opens the account record |
| Previous / Next | An adjacent page exists | Moves one page while retaining filters |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find account (`q`) | `User.username`, `first_name`, `last_name`, `email` | Text, max 150 | No | Case-insensitive substring search across these four fields |
| Role (`role`) | `User.groups` | All roles, Admin, Analyst, Auditor, Quality, Reviewer | No | Requires membership of the selected role |
| Status (`status`) | `User.is_active` | Any status, Active, Inactive | No | Filters account activation, not qualification or PIN status |
| Account | `User.username` | Text/link | — | Individual login identifier |
| Identity | `User.first_name`, `last_name`, `email` | Text | — | Full name and email; missing name shows Not supplied |
| Roles | `User.groups` | Group names | — | Displays current groups, or No role assigned |
| Status | `User.is_active`, `password_change_required` | Text | — | Active/Inactive plus Password change required when applicable |
| Last sign-in | `User.last_login` | Date/time and zone | — | Last login, or Never signed in |
| Matching accounts | — | Count | — | Count after filtering, across all pages |
| Page (`page`) | — | Integer | No | 30 accounts per page; defaults to page 1 |

## Rules and hidden logic

All accounts are listed by username, including inactive accounts and those without roles. Search terms are trimmed; filters combine. Invalid filter values show errors, no accounts and status 422. A nonnumeric page selects page 1; an out-of-range page selects the last page. Viewing/filtering changes no account and writes no account-management signature.

## Related pages

- [Account access](/accounts/access/)
- [Create account](/accounts/users/new/)
- Account record, opened through a username.
