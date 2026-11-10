# Functional research: manufacturing QC laboratory LIMS

Researched 2026-11-10. Drives requirements for Open Qual IQ. Synthetic data only. This document says what a QC lab needs; it makes no compliance or certification claim. Items tagged **[inference]** are the author's synthesis, not a sourced statement.

## Source quality and limits

| Source | Type | Weight | Caveat |
|---|---|---|---|
| [LabWare pharma / QA-QC](https://www.labware.com/industries/pharmaceutical), [LabWare QA/QC](https://portal.labware.cloud/qa-qc) | Vendor marketing | Medium | Feature lists, no detail; verify against docs |
| [LabVantage Stability brochure](https://www.labvantage.com/wp-content/uploads/2014/12/Stability1101JY25CYL.pdf), [LabVantage 8.9 notes](https://www.labvantage.com/blog/labvantage-lims-release-upgrade-to-8-9/), [LabVantage pharma QC blog](https://www.labvantage.com/blog/managing-quality-in-pharma-and-biopharma-labs/) | Vendor | Medium | Spec/sampling-plan versioning not documented publicly |
| SENAITE docs: [samples](https://www.senaite.com/docs/sample-basics.html), [partitions](https://www.senaite.com/docs/sample-partitions), [profiles](https://www.senaite.com/docs/analysis-profiles), [dynamic specs](https://www.senaite.com/docs/dynamic-analysis-specifications) | Open-source docs | High for what it covers | Clinical/contract-lab leaning; no lot disposition, stability, CoA-by-spec |
| [FDA OOS guidance, May 2022](https://www.fda.gov/media/158416/download) (via summaries; PDF not read in full) | Regulator guidance | High | US drug (CDER) context; re-read primary before encoding rules |
| [21 CFR 211.165](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/subpart-I/section-211.165) (summary read), 21 CFR 211.194 (older GPO editions only; check current eCFR), 21 CFR Part 11 (not fetched this session; [eCFR](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11)) | US regulation | High | Drug cGMP only; other industries (food, chemicals, medical devices, ISO 17025/9001) differ. Accessed 2026-11-10, US jurisdiction |
| STARLIMS v11 user manual (local, `/Users/gabriel/Downloads/usermanual`, ~870 pages) | Vendor manual, secondary | Low-medium | Untrusted data; used only to confirm module breadth and workflow shapes. No text, names or screens copied |

Not read: LabWare/STARLIMS/Thermo SampleManager proprietary docs (login-gated), Bika, ISO 17025 (paid). Thermo SampleManager was not researched beyond common knowledge, so it is not cited.

## Target: one system, all manufacturing QC segments (user decision 2026-11-10)

One product serves pharma/biotech cGMP, dietary supplements, food, chemical/industrial and medical devices. Segment differences are **configuration (rule sets)**, not code branches or separate products. One site/organization per deployment **[inference, carried from Open Roots IQ]**; a deployment may enable several segments at once (e.g. a supplement and food plant), so rule sets attach to products/sites, not to the installation.

### Segment profile: what actually differs

Regulatory claims below come from public summaries; primary eCFR text was not fully read. The product says "supports" only.

| Segment | Governing references (US, accessed 2026-11-10) | QC emphases that differ | Source |
|---|---|---|---|
| Pharma / biotech cGMP | 21 CFR 211 (esp. 211.165, 211.192, 211.194), FDA OOS guidance 2022; Part 11 | Full OOS Phase I/II, batch disposition by quality unit, stability, annual review, calibration and reagent records | [211.165](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-C/part-211/subpart-I/section-211.165), [FDA OOS](https://www.fda.gov/media/158416/download) |
| Dietary supplements | 21 CFR 111 (111.70/111.75 specifications and verification) | Identity test on every incoming dietary-ingredient lot; supplier CoA may supplement but not replace identity testing; supplier qualification; justified subset testing of finished batch with QC-approved rationale | [Part 111](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-111) (via secondary summary of 111.75) |
| Food | 21 CFR 117 (FSMA preventive controls: product testing and environmental monitoring as verification); not read in detail | Environmental monitoring (pathogen/indicator), hold-and-release on positive, allergen and micro tests, supplier verification | [Part 117](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-117) **[inference on detail; follow-up needed]** |
| Chemical / industrial | Mostly customer specs, ISO 9001 / ISO 17025-style practice, product standards (ASTM/ISO methods) | Spec per customer, grades, CoA per shipment to customer spec, lighter regulatory records; trending/SPC heavy | **[inference]**, no primary source read |
| Medical devices | 21 CFR 820 QMSR, effective 2026-02-02, incorporates ISO 13485:2016 by reference; Part 11 | Incoming inspection and acceptance records, lot/UDI-style traceability, nonconformance and CAPA links, risk-based supplier control, DHR/DMR references | [Part 820 eCFR](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-820), [summary of QMSR](https://www.tuvsud.com/en-us/knowledge-hub/articles/fda-qmsr-requirements-final-rule-effective-date-and-iso-13485-alignment) (consultancy; check Federal Register 89 FR 7496) |

Non-US regimes (EU GMP/Annex 11, ISO 17025 accreditation, ISO 13485 certification, FSSC/BRC) are out of scope of this research. **[inference]** The configurable rule-set model should leave room for them.

### What stays the same across segments (core, not configurable off)

Spec/test/result/review/disposition spine, immutable audit trail, PIN-based e-signatures, second-person review, versioned CoA, role-based access, synthetic-only demo data.

### What becomes configuration (rule set per segment, assignable per product/material/site)

| Configurable rule | Pharma | Supplement | Food | Chemical | Device |
|---|---|---|---|---|---|
| Required signature meanings/steps per workflow (analyst, reviewer, QA) | 2-3 | 2-3 | 1-2 | 1-2 | 2-3 **[inference]** |
| OOS procedure (phased investigation, retest rules, mandatory) | strict | strict | configurable | optional | strict, via nonconformance |
| Identity test mandatory on incoming lots; supplier CoA acceptance rules | yes | yes, CoA cannot replace | per supplier approval | per customer | per incoming inspection plan |
| Disposition vocabulary (Released/Rejected/Quarantine/Hold, Use-as-is...) | yes | yes | yes | yes | yes + rework/concession |
| Stability module on/off | yes | yes | shelf-life | optional | optional |
| EM module on/off | yes | optional | yes | no | optional |
| CoA template content/layout and customer-facing variants | yes | yes | yes | per customer | yes |
| Record retention period, review-by-exception, annual product review | yes | yes | yes | optional | yes |
| Deviation/CAPA depth (link-out vs built-in) | link/simple | link/simple | link/simple | optional | required link |

(Per-cell values are **[inference]** starting presets for seeded, editable rule sets; each must be checked against the segment's own regulation before a lab relies on it.)

**Design implication [inference]:** model a `RuleSet` (named, versioned, effective-dated) holding switches and parameters (required steps, signature meanings, retention, identity-test rule, OOS mode, enabled modules). Products or sites reference one; changing it is itself audited and e-signed. Ship editable presets named by segment, never hard-coded logic.

### Core: audit trail and PIN-based electronic signatures

Requirements for the shared core (supported by 21 CFR 211.194 records and Part 11 as the common reference; other segments commonly adopt the same pattern **[inference]**):

| Need | Detail |
|---|---|
| Audit trail | Append-only; who, when (server time, time zone), what entity, old value, new value, reason. Covers results, specs and spec versions, methods, status/disposition, rule sets, equipment status, user/role changes, signatures. Per-record history view, filterable, exportable; entries cannot be edited or deleted by any role |
| Signature meaning | Each signature records signer identity, timestamp, and meaning (authored, reviewed, approved, released) and the exact record version signed |
| PIN-based signing | At signing the user re-enters a signature PIN/credential (separate from the login password if desired) even when already logged in; PIN stored hashed with rate limiting and lockout; failed attempts are audited |
| Signature manifest | Signed records display signer name, date/time and meaning; signature is linked to the record and invalidated/flagged if the signed content changes **[inference, follows Part 11 intent]** |
| Separation of duties | Configurable per rule set; self-review blocked by default |
| Signing events | Required at review, approval, disposition, CoA release, spec approval, investigation conclusion, calibration acceptance (configurable) |
| Limits | The product supports a lab's Part 11-style controls; it does not claim Part 11 compliance. Identity proofing, PIN policy and account procedures are the lab's SOPs |

Part 11 primary text was not fetched this session; read [eCFR Part 11](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11) before finalizing signature requirements (notably 11.50, 11.70, 11.200, 11.300 on identification codes/passwords).

## Core user roles

| Role | Main work | Source basis |
|---|---|---|
| Sample custodian / receiving | Receive lots and samples, labels, storage, chain of custody | STARLIMS receive/inventory chapters; LabWare lot workflows |
| Analyst | Worksheets, results entry, calculations, instrument use | All vendors; SENAITE worksheets |
| Reviewer (second person) | Verify data, return or approve; cannot review own work | STARLIMS peer review rule (manual: person who entered results cannot approve them); SENAITE configurable required verifications |
| QC supervisor / manager | Queues, disposition, OOS/investigation ownership, spec approval | FDA OOS guidance (analyst + supervisor Phase I) |
| QA (quality unit) | Final lot disposition, deviations/CAPA, spec approval, audit-trail review | 21 CFR 211.165 (QC unit acceptance criteria) |
| Lab admin / config owner | Products, specs, methods, users, roles | All |
| Equipment / metrology owner | Calibration, maintenance schedules, reagent/standard inventory | 21 CFR 211.194; STARLIMS equipment chapters |
| Read-only (production, planner, auditor) | Lot status, CoA retrieval, audit view | **[inference]** |

## Functional areas (areas 1-21 plus 22 rule sets; see segment section above for what varies)

Legend: **M** = MVP, **L1** = first follow-up, **L2** = later.

| # | Area | What a lab needs | Phase | Rationale / evidence |
|---|---|---|---|---|
| 1 | Materials, products, **specifications** with versions | Material/product master; spec per product/stage with limit types (range, min/max, text/qualitative, % of label); effective dating; approval; results snapshot the spec version applied. STARLIMS separates limits from calculation/field "schemas"; SENAITE has valid vs warning ranges, dynamic spec import; LabWare flags OOS against predefined limits | M | Every judgement depends on it. Spec versioning in vendors is not publicly detailed, so versioning requirement is **[inference]** from record integrity (211.194 requires data against "established specifications") |
| 2 | **Test methods**, analytes, units, calculations | Method versions, analyte lists, units, calculations referencing other results, result qualifiers, rounding/significant figures, required analyst qualification | M | SENAITE calculations; STARLIMS test manager (analytes, methods, calcs); 211.194 requires record of method and any modification |
| 22 | **Configurable segment rule sets** | Named, versioned rule sets per segment (pharma, supplement, food, chemical, device) controlling signatures, OOS mode, identity-test rules, modules, retention; attach to product/site | M (engine + presets) | User decision 2026-11-10; design **[inference]** |
| 3 | **Sampling plans** and sample types | Plan per material/stage defining tests, sample counts, frequency; sample points; schedules that auto-create samples; profiles/templates ("recipes"); sub-sampling/aliquots (partitions); inspection-level plans (AQL-type); skip-lot | M basic (plan = test profile + spec per material/stage); L1 schedules, AQL, skip-lot | LabVantage sampling plans, skip-lot; STARLIMS sample points/schedules/ANSI inspection; SENAITE profiles & partitions |
| 4 | **Sample/lot receipt and login** | Receive raw-material lot (PO/supplier/lot/quantity), assign samples, labels, storage, status lifecycle, retains | M | Journey 1; STARLIMS receive-from-PO; 211.194(a)(1) requires source, quantity, lot, dates taken and received |
| 5 | **Results entry, worksheets/batches, QC samples** | Analytical batches/worksheets grouping tests across samples; blanks, controls, duplicates; templated layouts; manual entry plus file import; retests | M manual + worksheet; L1 file import | SENAITE worksheets with QC placement; STARLIMS batches/runs/QC manager |
| 6 | **Review and approval with PIN-based e-signatures** | Role-gated review, separation of duties, return with reason, signature meaning, PIN re-entry at signing (see Core section) | M (core) | Part 11 / Annex 11 support is a LabWare/LabVantage selling point; ELN-style approvals in STARLIMS |
| 7 | **Lot disposition** | Lot status (quarantine, released, rejected, hold, retest); disposition against spec by QA; blocks release while tests/investigations open; disposition history | M | LabWare lot disposition; 211.165 (batch must meet specs before release; failures rejected) |
| 8 | **CoA generation** | Templated PDF per lot/disposition; spec limits, results, method, signatures; versioned and immutable; amendment | M | LabWare CoA after validation vs spec; same version-and-supersede pattern as Open Roots IQ reports |
| 9 | **Audit trail** | Who/when/old/new/reason for every change; per-record history view; export (see Core section) | M (core) | 211.194; Part 11; STARLIMS per-batch traceability |
| 10 | **OOS/OOT investigations** | Auto-flag OOS; Phase I lab investigation then Phase II full investigation; retest/resample rules; invalidation only with documented lab error; linkage to lot disposition | M (flag, open, record, retest, conclude); L1 OOT/trend rules | FDA OOS 2022: documented investigation required for any OOS; no attribution to lab error without evidence. STARLIMS: investigation workflow init/preliminary/confirmatory/resample, retest averaging or replace. Retest-averaging is risky, **[inference]** make it explicitly configurable and audited |
| 11 | **Deviations and CAPA** | Own records or link to external QMS; link to lot, investigation, equipment | L1 (links in MVP, full module later) | Most firms keep QMS separate **[inference]**; offer reference fields and simple CAPA tracking first |
| 12 | **Equipment: calibration and maintenance** | Instrument register, schedules, due/overdue, calibration results vs tolerance, status gates use in results, usage log | M basic (register, due dates, block overdue use); L1 full maintenance | 211.194 requires periodic calibration records; STARLIMS equipment maintenance schedules |
| 13 | **Reagents, standards, inventory** | Receipt, lot, expiry, preparation/dilution lineage, usage in tests, expiry blocking | L1 (M if reagent traceability is required by owner) | 211.194 requires standardization records; STARLIMS inventory is a large module, so scope it narrowly |
| 14 | **Stability studies** | Protocol: conditions, time points, pull schedule, storage location, sample pulls, auto-created tests, shelf-life evaluation | L1 | LabWare, LabVantage (time zero, 3/6/12 months, protocol versioning in 8.9). Large, separable |
| 15 | **Environmental monitoring** | Sites/rooms/points, schedules, action/alert limits, excursions, trend by location | L1 or L2 | Open Roots IQ has none of this; STARLIMS EM chapter; LabWare EM |
| 16 | **Trending / SPC** | Control charts, zone rules, trend by spec/product/method; OOT alerts; QC sample charts | L1 | STARLIMS control charts with zone rules; 211.165 mentions statistical quality control criteria |
| 17 | **Analyst training/qualification** | Method-level certification, expiry, gate on assignment | L1 | STARLIMS analyst certifications; SENAITE none |
| 18 | **Dashboards, queues, alerts** | Role queues (pending review, due samples, OOS open, overdue calibration), turnaround, notifications | M queues; L1 KPIs | Vendor staples; STARLIMS dashboard branches and alerts |
| 19 | **Integrations** | ERP (lot/PO import, status export), MES, instrument/CDS files; API | L1 CSV/JSON import and REST read; L2 ERP/MES connectors | LabWare lists SAP, MES, Empower, Mettler; SENAITE JSON API and instrument import add-ons |
| 20 | **Document control, ELN** | Attached SOPs/method docs, form-driven ELN sheets | L2 (attachments M) | STARLIMS ELN is large; do not build a general ELN **[inference]** |
| 21 | Annual product review, genealogy, where-used | Cross-lot reports; supplier performance | L2 | LabWare mentions where-used, genealogy, annual review |

## Primary end-to-end journeys

1. **Raw material:** receive lot (PO, supplier, quantity) -> sampling plan creates samples -> assign tests from spec/method -> analyst tests on worksheet with QC -> second-person review -> compare to spec -> QA disposition (release/reject/hold) -> CoA (internal or supplier CoA compare) -> status visible to ERP/planner.
2. **In-process / finished goods:** scheduled or requested sample from sample point or batch -> same test/review path -> batch disposition -> finished-goods CoA, versioned.
3. **OOS:** result outside spec auto-flags and holds lot -> Phase I lab investigation -> invalidate (with documented lab cause) or confirm -> Phase II / deviation link -> retest per rule -> conclusion approved -> disposition unblocked.
4. **Stability (L1):** protocol -> pull schedule -> pulled samples -> tests -> trend vs shelf-life spec.
5. **Equipment/reagents (supporting):** calibration due -> record -> tolerance check -> instrument status changes -> blocks/permits use in results.
6. **Environmental monitoring (L1/L2):** schedule -> collect at point -> incubate/read -> action/alert limit evaluation -> trend.

## MVP definition

One journey end to end: **raw-material lot -> sample -> test -> review -> disposition -> CoA**, with OOS flag and basic investigation, spec versions, audit trail, e-signature at review/approval/disposition, basic equipment status and role queues. Matches how the vendors lead (lot management, specs, disposition, CoA) and makes the most reuse of Open Roots IQ's receipt -> batch -> review -> versioned report spine.

## Reuse hints from Open Roots IQ (skimmed `docs/product.md` only; verify in code)

| Open Roots IQ concept | Likely fit | Note |
|---|---|---|
| Receipt event with discrepancy dispositions | Strong | Adapt to lot receipt (PO, supplier, COA check) |
| Analytical batch with QC samples and QC evaluation against limits | Strong | Maps to worksheets/QC |
| Results with qualifiers, units, limits-applied snapshot | Strong | Add spec version reference |
| Analyst submit -> reviewer -> explicit release; no self-review | Strong | Core of review and disposition |
| Versioned immutable PDF report + amendment lineage | Strong | Becomes CoA |
| Audit trail (who/when/old/new/reason) | Strong | Required |
| Control charts, standards/reagents, instrument calibration (planned milestones 2-3) | Partial | Pull forward selectively |
| Client/COC/project, holding times, NELAP/EDD, MDL, permit reporting | Environmental-specific | Drop or replace: no clients-as-tenants, sample plan and lot replace COC; holding time becomes stability/retest dating |
| Missing entirely | New | Product/spec master, lot disposition, sampling plans, OOS investigation, stability, EM |

## Decisions for the owner

| # | Question | Default used here |
|---|---|---|
| 1 | Which rule-set presets to ship first: all five segments, or pharma + one other with the model proven? | Ship the engine plus editable presets for all five; validate depth for pharma first **[inference]** |
| 2 | Is stability/EM in the first release? | No, L1 (modules switchable per rule set) |
| 3 | Own deviation/CAPA module or link-out? | Link-out plus simple record; devices may require more |
| 4 | Reagent/standard traceability in MVP? | L1 |
| 5 | Supplier qualification and supplier CoA verification workflow? | L1, but the rule-set flag for identity-test-required is MVP |
| 6 | Signature PIN policy (separate PIN vs password, length, lockout, expiry)? | Separate hashed PIN, lockout after repeated failures, all audited |
| 7 | Non-US regimes (EU Annex 11, ISO 17025/13485 certification)? | Out of scope; leave room in rule sets |

## Evidence gaps

Thermo SampleManager and LabWare/STARLIMS primary docs were not read. Chemical/industrial segment rules and food Part 117 detail are inference or secondary. Segment regulation was read through search summaries only. Regulatory texts were read via search summaries; re-read the eCFR and FDA primary text before encoding any rule. Nothing here is a compliance claim.
