---
title: Organization sign-in
urls: accounts:single_sign_on
views: accounts.views.single_sign_on_page
templates: accounts/single_sign_on.html
models: accounts.User, accounts.SingleSignOnLink, core.AuditEvent
reviewed: 2026-11-16
---

## Purpose

Link your laboratory account to your account at your organization's identity provider, so that you can sign in there instead of typing your password. Unlink it again when you no longer want that. Your laboratory account, roles and signature PIN do not change.

## Who can use it

Any signed-in user, including an account with no laboratory role. It manages only your own link. The page exists only when the deployment configures single sign-on; otherwise it returns 404 and the **Organization sign-in** link on Account access is absent. A shared demonstration account cannot link or unlink: it sees **This is a shared demonstration account. Its password and signature PIN are published on the sign-in page and cannot be changed here.** with **Return without changes**, and a POST returns status 403.

## Layout

The **Account access** breadcrumb and an introduction are followed by a **Status** card and one form card.

- **Status** lists **Organization account** (the user name, verified email or name the provider gave when you linked, with the provider's subject below it, or **Not linked**), **Linked** and **Last sign-in with it** (date and time, or **Not yet**) when linked, and **Identity provider** (its display name and issuer address).
- When the link was made with a different provider than the one now configured, a warning says **This link was made with another identity provider (ISSUER) and no longer signs you in. Unlink it, then link your account at PROVIDER.**
- The form card is titled **Link your organization account** or **Unlink**. It asks for **Current password** and, when you have two-factor sign-in on, a code field. With a security key usable at this host name, a hint says to leave the code empty so the browser asks for the key; a notice appears if the browser cannot use keys.

## Actions

| Action | Shown when | Result |
|---|---|---|
| **Confirm** | Not linked | Checks your password (and second factor), then reloads this page with `?continue`: the form card is replaced by **Continue to PROVIDER**, which says the button works once, in this browser, for 10 minutes. Reloading that page sends no password or code again; once the request is used, expired or your account changed, the address shows the form again |
| **Continue to PROVIDER** | After **Confirm** | Opens the provider's sign-in. On return the link is made and you see **Your account is linked to LABEL. You can now sign in with PROVIDER. Other sessions have been signed out.** **Cancel** beside it reloads this page; the confirmation is then not used |
| **Unlink the organization account** | Linked | Checks your password (and second factor), removes the link and shows **Your account is no longer linked; PROVIDER no longer signs you in. Other sessions have been signed out.** |
| **Cancel** | Form shown | Returns to Account access |
| **Return without changes** | Shared demonstration account | Returns to Account access |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Current password | `User.password` (verified) | Masked text | Yes | Your login password, not your signature PIN |
| Code from your authenticator app or a recovery code (**Recovery code** without an app) | — | Text, max 64 | When two-factor sign-in is on, unless a key confirms | A current code or recovery code. A recovery code used here is spent. Empty means "use my key", which needs a key registered at this host name |
| action | — | Button value: `link` or `unlink` | Yes | The button pressed; only the one matching your current state is accepted, otherwise **The link changed meanwhile. Reload the page.** |
| security_key_response (hidden) | — | JSON from the browser | — | The key's answer, filled by the page's script |
| Organization account | `SingleSignOnLink.label`, `subject` | Text | — | The provider's user name, email (only when the provider marks it verified) or name for you at the time of linking, or the subject if it gave none; the subject, which is what identifies you, is shown below it |
| Linked / Last sign-in with it | `SingleSignOnLink.created_at`, `last_used_at` | Date and time | — | When the link was made and when it last signed you in |
| Identity provider | `SingleSignOnLink.issuer` | Display | — | The provider the link belongs to |

## Rules and hidden logic

- **Link flow**: you confirm your password, then a second factor when two-factor sign-in is on, then follow **Continue to PROVIDER**, sign in at the provider and come back. The answer must arrive in the same session within 10 minutes and is used once. The provider's identity is its issuer plus its subject; nothing else from the provider is trusted as identity.
- **One to one**: one laboratory account links to one organization account, and one organization account links to one laboratory account. No account is created and no role is given from the provider.
- **Wrong credentials**: a wrong password shows **Current password was not accepted.** and a wrong code or refused key shows the same messages as on Two-factor sign-in. They count toward the same failure limit and lock as sign-in; while the account is locked, even correct values are refused.
- **Refusals**: **Your account is already linked to an organization account. Unlink it first.**; **This organization account is already linked to another laboratory account.**; **Your account security changed since you confirmed your password. Start again.** (your password, two-factor sign-in or roles changed in another session while you were at the provider); **Linking started in another session or for another account. Start again.**; **The sign-in with your organization expired or was already used. Try again.**; **The answer from your organization's sign-in service was not accepted. Try again.**; **Sign-in at your organization was cancelled or not completed.**; **The organization's sign-in service could not be reached. Try again later.** Two-factor sign-in set up while you were confirming shows **Two-factor sign-in was set up meanwhile. Start again.**, and unlinking when nothing is linked shows **Your account is not linked to an organization account.** Failed forms return status 422; failures after the provider redirect return here with the message.
- **Effects**: linking or unlinking advances your management revision and session generation, so your other sessions end; this session continues. The attributed audit events are **account.single_sign_on_linked** and **account.single_sign_on_unlinked**, with the before and after account snapshot (`single_sign_on` holds the issuer, subject and label). They carry no electronic signature.
- **Before your code is checked**: the provider must be reachable and your account not already linked, so a code is not spent for nothing; **The organization's sign-in service could not be reached. Try again later.** is shown instead. After a failure the provider is asked again only after 30 seconds.
- **Password changes**: changing your own password keeps the link and reminds you of it, with its subject and date; an administrator's **Force password reset** or **Reset two-factor sign-in** removes it.
- **Other provider**: a link made with a different provider than the one configured is kept but no longer signs you in. Unlink it, then link again.
- **Not replaced**: signing in this way stands in for the password only. The second factor, when you have one, is still asked at sign-in, and the signature PIN is still entered for every signature. An administrator can remove your link on Account action.

## Related pages

- [Account access](/accounts/access/)
- [Sign in](/accounts/login/)
- [Two-factor sign-in settings](/accounts/two-factor/)
- Account action, where an administrator removes another account's link.
