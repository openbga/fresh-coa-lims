---
date: 2026-11-12
type: added
impact: medium
title: Publish a notice on the sign-in page with a signed change
area: Sign-in announcement
link: accounts:announcement
pr: 17
---
Administrators write, publish and withdraw one notice that is shown on the sign-in page. Each change needs a reason and a PIN signature and is kept in the audit trail. It is found under **Sign-in announcement** for the administrator role.

## Technical notes

- Sign-in announcement: one notice on the sign-in page that administrators write, publish and withdraw with a signed, audited change. The development seed can publish its non-administrator demo accounts there (`seed_demo --publish-accounts`).

Migration `accounts.0005_login_announcement` adds one table. Each change is signed with the meaning `announcement_authorized`, rechecks the reviewed revision and keeps the previous and new text in the audit trail. The text is escaped and then rendered with the page-documentation subset. `seed_demo --publish-accounts` lists the seeded non-administrator accounts with their shared password and PIN in the announcement, signed by `demo_admin`; it refuses to publish a credential that any administrator or superuser accepts and never replaces text an administrator saved.
