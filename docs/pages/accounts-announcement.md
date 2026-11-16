---
title: Sign-in announcement
urls: accounts:announcement
views: accounts.views.announcement
templates: accounts/announcement.html, accounts/includes/announcement.html
models: accounts.LoginAnnouncement, core.AuditEvent, core.ElectronicSignature
reviewed: 2026-11-12
---

## Purpose

Write, publish or withdraw the one notice shown on the sign-in page to anyone who opens it, before they sign in. Typical uses are a maintenance notice or, on a demonstration instance, the synthetic accounts visitors may use.

## Who can use it

Signed-in, active users with the explicit **admin** role. Others receive 403, including superusers without that role, and do not see the **Sign-in announcement** sidebar link. A pending required password change redirects to Change password first. Saving also needs your enrolled signature PIN.

## Layout

**Current announcement** shows the status (**Published** or **Not published**), whether the sign-in page shows the notice, and the revision. Below it the saved text appears exactly as visitors see it, or **No announcement text has been saved.**

**Change announcement** names you as signer with the meaning **announcement_authorized** and the revision being reviewed and bound. It warns that the text is public and links to PIN enrollment. With an enrolled PIN the form follows: title, announcement text, **Show on the sign-in page**, reason and your signing credentials, then **Cancel** and **Sign and save announcement**. Without one, the form is hidden and the page says **Enroll your signature PIN before changing the announcement.**

**Announcement history** lists every signed change, newest first, with its reason, actor, signature and **Inspect recorded values**. Its empty text is **No announcement changes recorded.**

## Actions

| Action | Shown when | Result |
|---|---|---|
| Sign and save announcement | You have an enrolled PIN | Saves the title, text and status together, signs the change and reloads this page with a confirmation |
| Cancel | With the form | Reloads the page with the saved values; nothing changes |
| Enroll or change your signature PIN | Always | Opens Signature PIN |
| Inspect recorded values | Each history entry | Shows the status, title and text before and after that change |
| Previous / Next | History has an adjacent page | Moves one page of history |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `LoginAnnouncement.published` | Published / Not published | — | Whether the sign-in page shows the notice now |
| Revision | `LoginAnnouncement.revision` | Integer | — | Starts at 1 and rises by one with every signed change |
| Title | `LoginAnnouncement.title` | Text, max 120 | No | Heading shown above the text |
| Announcement text | `LoginAnnouncement.body` | Text, max 4000 | When publishing | The notice. Blank lines separate paragraphs; lists, `\|` tables, bold, italic, inline code, fenced code and https or site-relative links are formatted |
| Show on the sign-in page | `LoginAnnouncement.published` | Checkbox | No | Checked publishes the text; unchecked keeps it here and shows visitors nothing |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the announcement is changed; kept with the history |
| revision | `LoginAnnouncement.revision` | Hidden integer | Yes | The revision you reviewed; a different current revision refuses the change |
| Signing username | — | Text | Yes | Your own username, typed again |
| Signature PIN | — | Masked digits | Yes | Your signature PIN; never shown again or stored in the history |

## Rules and hidden logic

There is exactly one announcement. Withdrawing it keeps the text for later republication. Title and text are trimmed and line endings normalized. Visitors see the text escaped first and then formatted, so HTML is displayed as typed and never interpreted; links with other schemes show as plain text.

Each save is one signed transition. The admin role and the reviewed revision are rechecked inside the transaction, and the new values, the audit event **signed.announcement_authorized** and the **announcement_authorized** signature commit together, bound to the new revision. The history keeps the previous and new title, text and status, and the audit trail shows the same values to everyone who can read it. History shows 20 changes per page.

Refusals return status 422 with your text kept and the PIN cleared, and change nothing: **Enter the announcement text before publishing it.**, **The announcement already has this text and status.**, **Record changed. Reload and review before signing.**, **Enter your own signing username and PIN.**, **Signature PIN was not accepted.** and **Signature PIN is temporarily locked.** A refused PIN still counts toward your PIN lockout and is recorded as **signature.denied**.

> The text is public and its history is permanent. Enter credentials only for synthetic demonstration accounts, and never for an account that holds the admin role. Not enforced by this page: it does not inspect what the text contains.

In a development instance or a demonstration deployment, `seed_demo --publish-accounts` can write the first announcement. It lists only seeded accounts that cannot change the announcement, stops them changing their own password and PIN, and never replaces existing text.

## Related pages

- [Sign in](/accounts/login/)
- [Signature PIN](/signature-pin/)
- [Users and roles](/accounts/users/)
- [Audit trail](/audit/)
