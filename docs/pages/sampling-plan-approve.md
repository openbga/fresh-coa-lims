---
title: Approve sampling plan version
urls: sampling:plan_approve
views: sampling.views.plan_approve
templates: catalog/approve.html
models: sampling.SamplingPlanRevision, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-15
---

## Purpose

Independent review and electronic signature that approves a draft sampling plan version. Approval freezes it so it can be used for lots.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden. The role is checked before the record is looked up, so a user without it gets 403 for existing and non-existent IDs alike; quality users get 404 for a missing ID. Reading roles other than quality cannot open this page.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- The signer must not be the author and must not have edited the draft (any earlier audit event on this version by you other than a signature). Then the page opens with status 403 and an explanation, and no form.
- Administrators get no exception: "Independent approval cannot be bypassed by any role, including administrators."
- The signing username you type must equal your signed-in username.

## Layout

- **Breadcrumbs**: Sampling, Sampling plans, plan code, "Version N · Approve".
- **Header line**: the version, "record revision N" and its status.
- **Content being approved**: Material and stage, Containers to sample, Minimum total amount, Instructions, Rationale, Effective, Record revision, Author.
- **Sign approval**: the statement of what your signature means ("approved", the record revision, the resulting revision and a content hash), "Signer:" with your name and username, and a link "Enroll or change your signature PIN".
- **Retires earlier** (information alert above the signer line, when this version overlaps approved versions): "This version overlaps the effective period of N approved version(s). Your signature also retires it/them:" then each version with "never applies: this version takes over before it starts", "stops applying on <time>" (this version's start, when it is still ahead) or "stops applying at the moment of your signature, because this version's start has already passed"; then "A retired version keeps its approved content and signature. Lots keep the versions frozen when their requirements were assigned; quality decides for each lot in testing whether to replace them."
- **Cannot be approved** (warning alert in place of the form): the refusal when a later-numbered approved version overlaps this one, with a **Back to <version>** button. No PIN is requested and a submission is not signed.
- **Form**: Approval comment, Signing username, Signature PIN. Buttons **Cancel** and **Sign and approve**.
- **Blocked state**: an alert "Not permitted" with the reason, and a button "Back to <version>" instead of the form.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Version is a draft and you are an independent quality user | Quality, not author or editor | Verifies your PIN, approves and signs; shows "Sampling plan <version> approved and signed." and returns to the sampling plan |
| **Cancel** | Form shown | Quality | Returns without signing |
| Enroll or change your signature PIN | Form shown | Signer | Opens the Signature PIN page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Approval comment | `AuditEvent.reason` | Text, max 2000 | Yes | Help: "What you checked before approving." |
| Signing username | — | Text, max 150 | Yes | Must match your signed-in username. |
| Signature PIN | — | Password (digits) | Yes | Your signature PIN; never stored or logged, re-entered every time. |
| Expected revision | — | Hidden integer | Yes | Record revision shown when the page opened; signing fails if it changed. |

## Rules and hidden logic

- **Draft only**: "Only draft revisions can be approved." (shown on the page as "Not permitted", and by the server).
- **Independence**: "You authored this revision; another quality approver must sign." or "You edited this draft; another quality approver must sign." The server rechecks at signing.
- **Stale record**: "Record changed. Reload and review before signing." if the record revision differs from the one shown.
- **Content checks at approval**: the parameter shape rules are rechecked ("Enter a positive count or percentage.", "A fixed plan needs a whole number of containers.", "A percentage cannot exceed 100.", "This basis takes no parameter.") and "Sampling instructions and rationale are required."
- **Retires overlapped versions**: approving does not refuse an overlap. Each approved version of the same sampling plan whose remaining period overlaps this one stops applying when this version takes over: at the later of this version's start and the moment of your signature, so never retroactively. A version that had not started yet never applies. Its approved content and signature are kept; only the moment it stops applying and the version that replaced it are recorded, and its effective period then shows "Superseded by version N from <time>" or "by version N before it took effect". A version already retired is only ever retired earlier. Nothing is retired when this version's own end has already passed. Lots keep the sampling plan version frozen when their requirements were assigned; quality decides for each lot in testing whether to replace them (Replace lot requirements). Approvals are serialised by a database lock so two approvals cannot race.
- **No retiring a later version**: "Version N is already approved for these dates, and a version cannot retire a later one. Withdraw this draft and create a new version." when an approved version numbered after this draft overlaps it. The page shows it before you sign; the server refuses the signature.
- **Preview and signing**: what the page lists is worked out when it opens. Signing works it out again at the moment of the signature, so the time shown for a version whose start has passed is the page's opening time, not the final one.
- **Signature and audit**: signature meaning is "approved". Each retired version gets audit event `revision.superseded` (before and after: superseded from, superseded by) with the reason "Superseded by the approval of <version>." followed by your comment, in the same transaction. The version becomes Approved, its content snapshot and SHA-256 hash are stored, the record revision increases by 1 and the signature binds to the new revision. Audit event `signed.approved` with your comment is written in the same transaction. Approved versions are immutable at the database level.
- **PIN and session**: "Enroll a signature PIN first." without a PIN; "Signature PIN was not accepted." for a wrong PIN (5 consecutive failures lock the PIN for 15 minutes: "Signature PIN is temporarily locked."); "Enter your own signing username and PIN." for a different username; "Session expired. Sign in again before signing." and "Sign in again before signing." for session problems. Failed PIN attempts and identity mismatches are audited even though the approval is refused.
- **Failed submission** returns status 422 with the form and an error summary; entries other than the PIN are kept.

## Related pages

- The sampling plan.
- [Signature PIN](/signature-pin/)
- [Audit trail](/audit/)
