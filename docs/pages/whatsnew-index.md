---
title: What's new
urls: whatsnew:index
views: whatsnew.views.index
templates: whatsnew/index.html, whatsnew/button.html
models: core.UserPreference
reviewed: 2026-11-17
summary: See what changed in OpenBGA QM LIMS, newest first: by month, then by impact, with what each change means for your work and where to find it.
---

## Common tasks
### See what changed since your last visit
1. Select [[What's new]] at the top right. A number beside it counts the changes you have not seen.
2. Read the changes marked [[New]] at the top of the most recent months.
### Find where a change is in the application
1. Under the change, select the page link (for example [[Material lots]]).
### Read the technical detail of a change
1. Under the change, select [[Technical notes]] to open settings, migrations and upgrade steps.
2. Select it again to close it.

## Good to know
- Opening this page clears the number beside [[What's new]] for your account, on every workstation you sign in at. A new account starts with no number.
- [[New]] marks the changes added since you last opened this page; it is gone on your next visit.
- Changes are ranked High, Medium or Low impact. High impact covers new workflows, removals, security fixes and anything a deployer must act on.
- A page link is shown only when your roles let you open that page.
- The same list is the repository's CHANGELOG.md. Nothing is fetched from the internet to show it.

## Purpose

Lists every change to the application that users, deployers or integrators can observe, so people know what they can do now, what behaves differently and where to find it.

## Who can use it

- Every signed-in user, with or without a laboratory role. Signed-out visitors are sent to Sign in.
- A user whose deployment requires two-factor sign-in and who has not set it up yet is sent to Two-factor sign-in first, as for every other page.
- Read-only: the page has no action that changes a record.

## Layout

- **What's new** in the top bar, before Theme, on every signed-in page: an icon with the text "What's new" on wide screens and a count badge when there are changes you have not seen. The badge shows up to 99, then "99+". Its tooltip and accessible name say "What's new: 3 new changes" (or "What's new" when there are none).
- Title "What's new" and one sentence; when changes arrived since your last visit it adds "N changes are new since you last opened this page."
- A warning notice "Some changes could not be read and are not listed." with one line per unreadable entry file, when there is one.
- With four or more months, a **Months** list of links to each month.
- One panel per calendar month, newest first. The panel title is the month ("November 2026") and beside it the dates its changes cover ("2026-11-03 to 2026-11-17", or one date).
- Inside each month, up to three sections in this order: **High impact**, **Medium impact**, **Low impact**. Empty sections are left out.
- Each change: its title, then its type as a status label with an icon (Added, Changed, Fixed, Removed, Deprecated or Security; Security in red, Deprecated in amber), **New** when it is new to you, the date, the area of the application when given, and **Pull request #N** when given; then its summary, the page link when there is one and you may open it, and **Technical notes** (closed) when it has any.
- Empty state "No changes are recorded yet" when there are no changes.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **What's new** (top bar) | Signed in | Everyone | Opens this page |
| Page link under a change | The change names a page and your roles show that page in the sidebar | Everyone allowed | Opens that page |
| **Technical notes** | The change has technical notes | Everyone | Opens or closes them; nothing is saved |
| **Pull request #N** | The change names a pull request | Everyone | Opens the pull request in the public source repository |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Title | — (entry file) | Text | Yes | What changed, in plain words |
| Type | — (entry file) | Added, Changed, Fixed, Removed, Deprecated, Security | Yes | The kind of change |
| Impact | — (entry file) | High, Medium, Low | Yes | Groups the change inside its month |
| Date | — (entry file) | Date (YYYY-MM-DD) | Yes | The day the change was merged |
| Area | — (entry file) | Text | No | The part of the application, as named in the sidebar |
| Summary | — (entry file) | Text | Yes | What you can do now or what behaves differently |
| Technical notes | — (entry file) | Text | No | Settings, migrations, schema identifiers, dependencies, upgrade steps |
| Last seen | `UserPreference.value` (key `whatsnew.seen`) | Entry identifier | — | The newest change you were shown; set on the first page you open and whenever you open this page |

## Rules and hidden logic

- **Source**: each change is one file in `changelog.d/` that ships with the application. The page and the repository's CHANGELOG.md are built from the same files in the same order. No network request is made.
- **Order**: months newest first; inside a month High, Medium, then Low impact; inside an impact, newest first, then by title.
- **Unread count**: changes whose identifier (date, then name) is later than the last one you were shown. The first page you open after your account is created records the newest change as seen, so a new account shows no count and no **New** labels; the list still shows every change.
- **Clearing**: opening this page records the newest change as seen for your account (a presentation preference, stored on the server so it follows you between workstations). No audit event is written; the browser cannot set this value.
- **Unreadable entries**: an entry file that breaks the format is left out and named in the warning notice; the rest are listed.
- **Links**: a page link is shown only when the sidebar would show that page's section to you; the page itself still checks your access.

## Related pages

- [Dashboard](/)
- [Account access](/accounts/access/)
