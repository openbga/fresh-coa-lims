---
title: Change announcement
urls: accounts:announcement_change
views: accounts.views.announcement_change
templates: accounts/announcement_change.html
models: accounts.LoginAnnouncement, core.AuditEvent, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-17
summary: Sign a change to the sign-in announcement: its title, text and whether the sign-in page shows it. Admin role only.
---

## Common tasks
### Publish or update the notice
1. Enter an optional [[Title]] and the [[Announcement text]], and check [[Show on the sign-in page]].
2. Enter a [[Reason]], your [[Signing username]] and [[Signature PIN]], then select [[Sign and save announcement]].
### Withdraw the notice
1. Uncheck [[Show on the sign-in page]], enter a [[Reason]] and your signing username and PIN.
2. Select [[Sign and save announcement]]. The text is kept for later.
### Leave without changes
1. Select [[Cancel]] to return to the announcement.

## Good to know
- The text is public: anyone who opens the sign-in page sees it. Never enter personal data, or the password or PIN of a real account.
- If someone saved a change after you opened this, yours is refused. Reload and review before signing again.
- A refused PIN still counts toward your PIN lockout, and nothing is saved.
- Saving needs your own enrolled signature PIN.

## Purpose

Change the one notice shown on the sign-in page, with a reason and your electronic signature. It opens in the form dialog over Sign-in announcement; this page is the fallback without JavaScript.

## Who can use it

Signed-in, active users with the explicit **admin** role. Others receive 403, including superusers without that role. Without an enrolled signature PIN the page explains **Enroll your signature PIN before changing the announcement.** and shows no form.

## Layout

A signing card (the signature band with "Change announcement"). Its summary states the meaning **announcement authorized**, the revision being reviewed and the revision the signature binds; warns that the text is public and stays in the audit trail; names you as signer and links to PIN enrollment. Then the form: **Title**, **Announcement text**, **Show on the sign-in page**, **Reason**, **Signing username**, **Signature PIN**, then **Cancel** and **Sign and save announcement**.

## Actions

| Action | Shown when | Result |
|---|---|---|
| Sign and save announcement | You have an enrolled PIN | Saves the title, text and status together, signs the change and returns to Sign-in announcement with "Announcement saved. It is shown on the sign-in page." or "Announcement saved. The sign-in page shows no notice." |
| Cancel | With the form | Returns to Sign-in announcement; nothing changes |
| Return without changes | No enrolled PIN | Returns to Sign-in announcement |
| Enroll or change your signature PIN | Always | Opens the PIN form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Title | `LoginAnnouncement.title` | Text, max 120 | No | Heading shown above the text |
| Announcement text | `LoginAnnouncement.body` | Text, max 4000 | When publishing | The notice. Blank lines separate paragraphs; lists, `\|` tables, bold, italic, inline code, fenced code and https or site-relative links are formatted |
| Show on the sign-in page | `LoginAnnouncement.published` | Checkbox | No | Checked publishes the text; unchecked keeps it and shows visitors nothing |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the announcement is changed; kept with the history |
| revision | `LoginAnnouncement.revision` | Hidden integer | Yes | The revision you reviewed; a different current revision refuses the change |
| Signing username | — | Text | Yes | Your own username, typed again |
| Signature PIN | — | Masked digits | Yes | Your signature PIN; never shown again or stored in the history |

## Rules and hidden logic

Each save is one signed transition. The admin role and the reviewed revision are rechecked inside the transaction, and the new values, the audit event **signed.announcement_authorized** and the **announcement_authorized** signature commit together, bound to the new revision. Title and text are trimmed and line endings normalized.

Refusals return status 422 with your text kept and the PIN cleared, and change nothing: **Enter the announcement text before publishing it.**, **The announcement already has this text and status.**, **Record changed. Reload and review before signing.**, **Enter your own signing username and PIN.**, **Signature PIN was not accepted.** and **Signature PIN is temporarily locked.** A refused PIN is recorded as **signature.denied**.

## Related pages

- [Sign-in announcement](/accounts/announcement/)
- [Signature PIN](/signature-pin/)
