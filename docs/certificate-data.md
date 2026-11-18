# Certificate data

Each certificate of analysis version issued or amended by OpenBGA QM LIMS carries its content in a machine-readable form: one JSON document, schema `oq.certificate-data/1`. It is written once, when the version is signed, from the evidence the signature covers, and never changes. This page is the contract for people and systems that read it: what it holds and how to rely on it. [product.md](product.md) explains the feature.

## Where it is

- **In the PDF.** The issued PDF carries the document as the attached file `certificate-data.json`, related to the PDF as its *Data* (PDF/A-3 associated file). Any PDF reader lists it among the attachments; `pdfdetach -saveall certificate.pdf` extracts it.
- **Beside the PDF.** Staff who read certificates download the same bytes from the version page or the certificate page (**Download data**), as `<certificate number>-v<version>.json`.
- **In the lot record.** The export of a lot's complete record holds it as `files/certificates/<certificate number>-v<version>-data.json`.

The copy attached to the PDF and the downloaded copy are the same bytes. Staff see their SHA-256 on the version page (*Certificate data SHA-256*), stored when the version was signed; a file whose SHA-256 differs is not the data of that certificate.

A version issued before certificate data existed has no data. Its PDF is the issued record.

## Conventions

| Topic | Convention |
|---|---|
| Encoding | UTF-8 JSON, indented, keys in the order below. Compare documents by their bytes or their SHA-256, not by re-encoding them |
| Values | Results, replicates and limits are text exactly as recorded and reported (`"99.60"`, `"<10"`, `"Conforms"`); they are never floating-point numbers |
| Times | ISO 8601 in UTC to the second, as the certificate prints them (`2026-11-18T10:03:05Z`); dates as `YYYY-MM-DD` |
| Absent | A value the certificate does not state is `null`; a list with no entries is `[]` |
| Scope | What the printed certificate states, and nothing more. No internal record numbers, except inside identifiers the certificate prints (a requirement source names the catalog version it came from) |
| Outcomes | `conforms`, `does_not_conform`, `not_judged` (with `reason`), `information` (stated for information only), `not_tested` |

## Content

| Key | What it holds |
|---|---|
| `schema` | `oq.certificate-data/1` |
| `certificate` | `number`, `version`, `kind` (`issue` or `amendment`), `amends_version` and `amendment_reason` for an amendment, `recipient` (or null for a general certificate), `scope` (the customer or market scope the certificate is for, or null for all of the lot's requirements), `issued_by`, `issued_at`, `remarks`, `statement` (what the certificate does and does not attest), `synthetic_data` and `notice` |
| `lot` | `number`, `material`, `state`, `received_at`, `received_by`, `expiry_on`, `retest_on`, and `reassessment` when a reassessment gave the retest date |
| `disposition` | The signed QC disposition: `decision`, `signer`, `signed_at`, `lot_revision` |
| `rules` | The lot's rule set: `code`, `version`, `revision`, `segment`, effective period and `required_tests` (null on a certificate for one scope) |
| `additional_rules` | Additional rule sets that apply to the lot (empty on a certificate for one scope) |
| `specifications` | `code`, `version`, `scope` and `sha256` of each specification version the certificate reports against |
| `methods` | `code`, `version`, controlled `document`, `suitability`, `batch_qc_required` with the number of `batch_qc_checks`, and `sha256` of each method version, once each; a method the snapshot gives as text is `{"text": ...}` |
| `requirement_decisions` | Where the lot's specifications state a test differently: the statement applied, those not applied and the signed decision |
| `results` | The laboratory's results: `test`, `name`, `sample`, `method`, `contract_laboratory` (who performed the test, when not this laboratory), `replicates`, `reportable`, `unit`, `limits` (the printed `acceptance` text, and numeric limits as values with whether each boundary is included) and the independent `review` |
| `supplier_results` | Results stated on a supplier's certificate and accepted in place of a test: what the supplier `stated`, the `specification` it is compared with (as printed), the supplier's certificate, the supplier, the qualification and who `accepted` it |
| `not_tested` | On a certificate for one scope: tests its specification states that the lot has no result for (such a certificate is not issued, so this is empty on an issued one) |
| `conformity` | On a certificate of all of the lot's requirements, for a lot under more than one specification: each result against every specification that states its test |
| `decision_rule` | How conformity is judged, as printed, or null when the certificate states no conformity |
| `sample_results` | Only for a certificate of the development-only manual journey, which has no `results`: its samples, each with its results, limits and reviews |
| `holds` | Whether hold status is `asserted`, and the holds: each `hold` as printed (its description, or its identifier when it has none) and its `status` |
| `investigations`, `corrections` | As printed |
| `signatures` | Each signature manifestation the certificate prints: `meaning`, `signer`, `signed_at`, `bound_to` |
| `identifiers` | `evidence_sha256`, `assignment_sha256` and the `requirement_sources` the certificate prints, in order (a source repeated by the next result once) |

On a certificate for one scope, each laboratory result and each supplier result carries `conformity`: the result as judged against that scope's specification, with its requirement and outcome. Its `reportable` and `limits` are null there, because the values the lot was released against may be another specification's, which that certificate does not name; for the same reason its `conformity` does not say whether that specification was the one applied to the lot. On the certificate of all of the lot's requirements, `conformity` lists every specification's statement and says which one was `applied`, as the printed table does.

## Changes to the format

A change that removes or renames a key or changes what a value means gets a new schema name (`oq.certificate-data/2`); versions already issued keep theirs. A key may be added without a new name, so a reader checks `schema` first and ignores keys it does not know.
