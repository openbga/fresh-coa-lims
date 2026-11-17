---
title: Sign-in announcement
urls: accounts:announcement
views: accounts.views.announcement
templates: accounts/announcement.html, accounts/includes/announcement.html
models: accounts.LoginAnnouncement, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-17
summary: The one notice shown on the sign-in page to anyone who opens it, before they sign in. See it as visitors do and every signed change; change it from the header. Admin role only.
---

## Common tasks
### Publish, update or withdraw the notice
1. Select [[Change announcement]] in the header.
2. In the dialog, edit the text, check or uncheck Show on the sign-in page, enter a reason and your signing username and PIN, then select Sign and save announcement.
### See what changed and who signed
1. In Announcement history, select [[Inspect recorded values]] on a change to see the status, title and text before and after it.
### Enroll your PIN first
1. If Change announcement is missing, the page says why: enroll your signature PIN on the Signature PIN page.
## Good to know
- The text is public: anyone who opens the sign-in page sees it. Never enter personal data, or the password or PIN of a real account.
- Every change stays in the history and the audit trail, including text you later replace or withdraw.
- HTML is shown as typed, never interpreted. Lists, tables, bold, italic, code and links are formatted.
- Withdrawing the notice keeps its text here for later.

## Purpose

Write, publish or withdraw the one notice shown on the sign-in page to anyone who opens it, before they sign in. Typical uses are a maintenance notice or, on a demonstration instance, the synthetic accounts visitors may use.

## Who can use it

Signed-in, active users with the explicit **admin** role. Others receive 403, including superusers without that role, and do not see the **Sign-in announcement** sidebar link. A pending required password change redirects to Change password first. Saving also needs your enrolled signature PIN.

## Layout

The page opens with "One notice shown on the sign-in page to anyone who opens it, before they sign in. Changing it requires a reason and your signature PIN."

The header has one action, **Change announcement**, which opens the signed change in the form dialog (Change announcement). Without an enrolled signature PIN the action is not shown and a notice says **Enroll your signature PIN before changing the announcement.**

**Current announcement** shows the status (**Published** or **Not published**), **Sign-in page** ("Shows the notice below" or "Shows no notice"), and the revision. Below it the saved text appears exactly as visitors see it, or **No announcement text has been saved.**

**Announcement history** lists every signed change, newest first, titled "Announcement published", "Announcement withdrawn", "Published announcement changed" or "Unpublished text changed", with its time, reason, actor, signature and **Inspect recorded values**, then the history's pager. Its empty text is **No announcement changes recorded.** After saving, the page says "Announcement saved. It is shown on the sign-in page." or "Announcement saved. The sign-in page shows no notice."

## Actions

| Action | Shown when | Result |
|---|---|---|
| Change announcement | You have an enrolled signature PIN | Opens Change announcement in the form dialog (its own page without JavaScript) |
| Inspect recorded values | Each history entry | Shows the status, title and text before and after that change |
| First / previous / next / last page | History has more than one page | Moves through the history |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `LoginAnnouncement.published` | Published / Not published | — | Whether the sign-in page shows the notice now |
| Sign-in page | `LoginAnnouncement.published` | Text | — | "Shows the notice below" or "Shows no notice" |
| Revision | `LoginAnnouncement.revision` | Integer | — | Starts at 1 and rises by one with every signed change |

## Rules and hidden logic

There is exactly one announcement. Visitors see the text escaped first and then formatted, so HTML is displayed as typed and never interpreted; links with other schemes show as plain text. Every change is a signed transition made on Change announcement; this page records nothing. History shows 20 changes per page, newest first.

> The text is public and its history is permanent. Enter credentials only for synthetic demonstration accounts, and never for an account that holds the admin role. Not enforced by this page: it does not inspect what the text contains.

In a development instance or a demonstration deployment, `seed_demo --publish-accounts` can write the first announcement. It lists only seeded accounts that cannot change the announcement, stops them changing their own password and PIN, and never replaces existing text.

## Related pages

- Change announcement (the signed change)
- [Sign in](/accounts/login/)
- [Signature PIN](/signature-pin/)
- [Users and roles](/accounts/users/)
- [Audit trail](/audit/)
