---
date: 2026-11-19
pr: 67
type: added
impact: high
title: Plan proficiency testing and interlaboratory comparisons, and review their outcomes
area: Specifications and methods
link: catalog:proficiency_list
---
Under **Specifications and methods > Proficiency testing**, quality plans each method's participation in a proficiency testing round or another interlaboratory comparison, with the day results are due; **Reminders** list results falling due or overdue. The laboratory records its report and each result with the provider's score, and a quality person who recorded and performed none of it reviews the outcome with a signature. An unsatisfactory result needs corrective follow-up (cause, actions, results already reported, effectiveness), closed with a signature by another quality person; the **Methods** list shows each method's last outcome and next round.

## Technical notes

- Migration `catalog.0011` adds `catalog_proficiencyparticipation` and `catalog_proficiencyresult` with database guards: a participation is never deleted, a reviewed one changes only its follow-up and closure, a closed or cancelled one never changes, and results are added or removed only while it is open and never updated. A check constraint ties each z, z′, ζ or En score to its outcome. No existing row changes.
- The review signature (meaning `reviewed`) freezes `oq.proficiency/1`; the closure (meaning `closed`) freezes `oq.proficiency-follow-up/1`. New audit actions: `participation.planned`, `participation.plan_changed`, `participation.plan_corrected` (a plan change once results or the report are recorded, which counts as authorship), `participation.report_recorded`, `participation.result_added`, `participation.result_removed`, `participation.follow_up_recorded` and `participation.cancelled`.
- New lookup `impact-assessments` for the follow-up's impact assessment; reminders take the kind `proficiency`.
