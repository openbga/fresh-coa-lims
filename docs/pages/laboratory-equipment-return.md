---
title: Return equipment to service
urls: laboratory:equipment_return
views: laboratory.views.equipment_return
templates: ops/sign.html
models: laboratory.Equipment, core.ElectronicSignature
reviewed: 2026-11-11
---

## Purpose

Approve returning equipment to service after assessing the impact of its failure or removal, with meaning **approved**.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- A Quality user who removed the equipment from service (or whose calibration failure took it out; the status change is attributed to the recorder) cannot return it ("The person who removed equipment from service cannot return it."); equipment already in service shows "Equipment is already in service.". Both show the reason and no PIN control (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): the asset and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Description / Current state | `Equipment.description` and fitness | Display | — | The equipment and its fitness label (not the raw service state) |
| Impact scope | — | Display | — | How many failed calibrations and recorded uses this return assesses |
| Signing username | — | Text | Yes | Must equal your own username |
| Impact assessment | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Equipment.revision` | Integer | Yes | Revision shown when the page opened |
| Assessed scope (hidden) | — | Record numbers | Yes | The affected uses and failed calibrations counted when the page opened; must still match when you sign |

## Rules and hidden logic

- **Preconditions**: currently out of service ("Equipment is already in service."); you are not the person who removed it ("The person who removed equipment from service cannot return it."); the latest counting calibration is a pass ("A passing calibration after any failure must be independently accepted first.") and not expired ("The latest accepted calibration has expired."); approved current qualification when required ("Approved, current qualification evidence is required.").
- The impact assessment you type is stored with the failed calibrations and the recorded uses since the last accepted passing calibration before the earliest failure that no signed return to service has assessed yet ("Failed calibrations assessed: …", "Affected uses assessed: …"). A later passing calibration does not shrink that list. The scope counted when the page opened is submitted with the form and compared under the equipment lock; if a failure (for example a late entry of an earlier failed calibration) or use was recorded after the page opened: "Recorded uses or failures changed while you assessed them. Reload and reassess." A missing or malformed scope: "The assessed scope is missing or invalid. Reload and reassess." Qualification must be approved and inside its validity dates.
- On success the equipment is In service, with you recorded as the person and time of the status change. Success message: "Equipment returned to service." The failures and uses assessed are listed on the equipment record before you sign, and the closed assessment window starts after this signature.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Equipment record
