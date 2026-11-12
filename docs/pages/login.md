---
title: Sign in
urls: login
views: django.contrib.auth.views.LoginView
templates: registration/login.html
models: accounts.User
reviewed: 2026-11-11
---

## Purpose

Sign in to OpenBGA Fresh CoA LIMS with the individual account issued by your laboratory administrator.

## Who can use it

Anyone can open the entrance page. Signing in requires an active account and its correct password. Laboratory roles determine access after sign-in; a superuser has no implicit laboratory authority. There is no public signup.

## Layout

On wide screens, an illustrative manufacturing cutaway appears beside the sign-in panel. It depicts production equipment, a packaging line and a quality-control laboratory. The illustration changes from morning to dusk with the theme. On narrower screens it is hidden so the form remains the focus.

The page shows the certificate-and-leaf mark and **OpenBGA Fresh CoA LIMS** name, **Sign in**, account guidance, and the licence and **Source code** footer. The **Theme** menu is at the upper right. Validation and session messages appear with the form. This entrance page is outside the signed-in workspace and does not show the page-documentation panel.

## Actions

| Action | Result |
|---|---|
| Sign in | Validates the credentials and opens the requested local page, or Material lots by default |
| Theme | Choose Light, Dark or System; the browser remembers the choice |
| Source code | Opens the source repository configured for this deployment |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Username | `User.username` | Text | Yes | Your individual account identifier |
| Password | `User.password` | Masked text | Yes | Your login password; it is not your signature PIN |
| next | — | Hidden local destination | No | Returns you to the requested page after sign-in when the destination is allowed |

## Rules and hidden logic

Incorrect credentials and inactive or temporarily locked accounts are refused. Repeated failed password attempts temporarily pause password sign-in for that account. Rejected forms retain the username and clear the password. Ask your laboratory administrator for account provisioning or recovery.

A successful sign-in starts a controlled session. Accounts requiring password replacement go to Change password before entering the workspace. An account without a recognized laboratory role reaches Account access from the workspace entry point. Each destination still checks its own permissions. Signing in does not approve a scientific record or apply an electronic signature.

## Related pages

- [Material lots](/)
- [Account access](/accounts/access/)
- [Change password](/accounts/password/)
