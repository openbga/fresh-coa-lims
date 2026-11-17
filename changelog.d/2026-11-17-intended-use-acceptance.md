---
date: 2026-11-17
type: added
impact: high
title: Record and accept the system's intended use
area: Validation
link: validation:use_list
pr: 43
---
Under **Validation**, quality records what the system is used for and what is outside it, and a different quality person accepts it with a signature. The acceptance freezes the approved versions in force and the running release, and the list shows what changed since.

## Technical notes

- Validation records of the laboratory, under the new sidebar item **Validation** (app `validation`). **Intended use** (`validation:use_list`, `use_new`, `use_detail`, `use_accept`, `use_withdraw`): quality records what the system is used for and what is outside it, the supported assays (methods with an approved version in force), the process owner and the system owner, other responsibilities, the validation report and the known issues and conditions; a different quality person accepts it with a signature that freezes every approved rule set, specification, method, sampling plan and stability protocol version in force and the running release (`SOURCE_REVISION` or `RENDER_GIT_COMMIT`), and supersedes the previous acceptance. The list and the accepted record show what changed since.
- New tables `validation.UseAcceptance`, `validation.Rehearsal` and `validation.RehearsalFile` (migrations `validation.0001_initial` and `validation.0002_guards`, whose triggers keep recorded content immutable, allow only the signed or withdrawn transitions and keep evidence files append-only).
- New audit actions `use_acceptance.recorded`, `use_acceptance.superseded`, `use_acceptance.withdrawn`, `rehearsal.recorded`, `rehearsal.file_attached` and `rehearsal.withdrawn`; the acceptances are `signed.accepted`.
