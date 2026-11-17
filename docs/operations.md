# Operations and recovery

This runbook covers the PostgreSQL 17 application and its Render deployment configuration. The procedures below are not themselves execution evidence; execute and record them in your own deployment. Keep executed checks, timestamps, operators, source revision, archive checksum and outcomes in restricted operational evidence. Do not place credentials or database archives in Git.

A restore rehearsal takes a backup with its manifest (`backup_manifest`), restores it into a new database and checks the copy against the manifest (`verify_restore`). The check covers table fingerprints, schema parity (columns, constraints, indexes, triggers and functions), sequences, signature and audit binding, stored certificate and raw-data checksums, enabled triggers, the migration state and the Django system checks, and it writes a report to keep as evidence. A full migration of every registered app is covered by a fresh install.

Use a fixture that exercises every populated workflow you rely on: approved native specifications, analytical observations, QC and OOS records, laboratory resources and qualifications, stability records and issued PDFs. Test negative trigger mutations, point-in-time recovery, encrypted off-machine backups, runtime-role separation, identity recovery and file media restoration separately. A rehearsal that uses the trusted service channel does not exercise interactive username/PIN signing. A rehearsal alone does not establish RPO/RTO or production recovery acceptance.

## Bootstrap account access

In the intended instance's application shell, after migrations, create the individual bootstrap account and explicitly assign its laboratory role:

```sh
python manage.py createsuperuser --username admin
python manage.py assign_roles admin admin --actor admin --reason 'Bootstrap account administration'
```

Replace both occurrences of `admin` that identify the account if using another username; the role argument remains `admin`. For local development prefix commands with `uv run`. The assignment records the actor, prior/new roles and reason in the audit trail. `assign_roles` replaces the complete role set, so include every intended role when updating an existing account.

`createsuperuser` alone grants no laboratory role. The laboratory `admin` role permits reading every area (including audit export and CoA PDF) and account administration, not scientific mutation; those still require explicit roles and independent actors. It does not grant Django `is_staff` or superuser status. The signed-in **Account access** page explains missing roles and links authorized staff administrators to the existing read-only Django account view. Explicit admins also see **Users and roles**, the signed web management interface. A superuser without the explicit role sees bootstrap guidance but cannot use that interface. Users without a role should ask their organization's account administrator; the access page and sign-out remain available.

For an authorized synthetic demonstration in `DEBUG=true`, run `python manage.py seed_demo --actor admin --journey` only after the bootstrap sequence. The command accepts a superuser actor without the `admin` role but warns that the actor still lacks it; it never assigns roles to that actor. Seeding is deliberate and is not part of deployment or regulated production setup. `--publish-accounts` additionally writes the seeded non-administrator accounts, their shared password and their PIN into the sign-in announcement, signed by `demo_admin`, whose own credentials must differ (`DEMO_ADMIN_PASSWORD`, `DEMO_ADMIN_PIN`). Use it only on an instance meant to be open to anyone who can reach it. The published accounts can no longer change their own password or PIN or set up two-factor sign-in; an administrator's forced password reset or PIN re-enrollment ends that for an account.

## Signed account administration

Accepted limitation: administrators are trusted to perform account administration. An admin who sets an initial or temporary password and requires PIN re-enrollment could act as that account. The application does not prevent this; laboratory SOPs and review of the audit trail (including `account.created`, `account.reset_password` and `account.reenroll_pin`) are the mitigations.

Enroll the administrator's own PIN at `/signature-pin/` by confirming the login password, then use **Users and roles**. Keep a second individually verified active admin for recovery. The service refuses self-granted additional roles and deactivation/removal of the last active admin; these checks also apply to the audited role command. Only the initial roleless-superuser bootstrap may self-assign exactly `admin` when no active admin exists.

| Action | Required operation and effect |
|---|---|
| Create account | Verify identity, enter the initial password privately, select roles, give a reason and sign. Share credentials through an approved private channel; the user must replace the password before workspace access |
| Assign/revoke roles | Review the complete replacement set, reason and sign. Admin alone grants no scientific authority |
| Deactivate/reactivate | Reason and sign; deactivation refuses login and both actions invalidate earlier sessions |
| Clear PIN lockout | Verify the individual's identity and investigate failed signing, then reason and sign; clears the signing lock without revealing/replacing the PIN |
| Require PIN re-enrollment | Reason and sign; removes the old hashed credential. The owner must enroll a new PIN with their current login password |
| Force password reset | Reason and sign; optionally enter a private temporary password. If left blank, the user signs in with their current password. Either way, replacement is mandatory before workspace access; the application sends no email |
| Change own password | Confirm the current password and provide a reason; no PIN is required for this recovery-capable operation. Only the current session is retained |
| Change sign-in announcement | Enter or edit the title and text, choose whether the sign-in page shows it, give a reason and sign. The text is public before sign-in and its earlier versions stay in the audit trail |

Every administrative web change signs the account revision with meaning `account_authorized` and records safe before/after values. A sign-in announcement change signs the announcement revision with meaning `announcement_authorized` and records the previous and new text. The account detail history shows this evidence; no password, PIN or credential hash is exposed. All account-management changes revoke existing target sessions on their next request; signatures additionally check revocation inside their transaction. Self-administration signs out the actor immediately. A stale page must be reloaded and reviewed before signing. Installing this release invalidates older sessions without account security epochs. Trusted `create_staff`/`assign_roles` operator commands remain audited but unsigned; restrict application-shell access and document its use under the recovery procedure.

## Responsibilities and recovery decisions

| Owner | Required decision or evidence |
|---|---|
| Deployment operator | Exact deployed commit/image, configuration, migration history, database identity and recovery access |
| Quality owner | Acceptable recovery point, records affected by a loss, reconciliation and release of recovered service |
| Security/account owner | Individual identity verification, access review, credential recovery, incident handling and session policy |
| Backup operator | Approved encrypted backup destination, access, retention, schedule and restore rehearsals |

The organization must set RPO/RTO and retention schedules before relying on this service. A local Docker volume is persistence, not an independent backup. PostgreSQL logical dumps cover one database, not cluster roles or external storage; retain controlled infrastructure/configuration records separately. `pg_dump -Fc` creates a consistent custom-format archive while normal activity continues. Use PostgreSQL 17 tools for this deployment; the application image includes them. [PostgreSQL 17 pg_dump documentation](https://www.postgresql.org/docs/17/app-pgdump.html), accessed 2026-11-10.

## Backup with a manifest

`backup_manifest` records what the database holds when a backup is taken; `verify_restore` checks a restored copy against that record. Both only read the database, and both work for a role that may only read it. Run them with the release that serves the database, from its application shell or image, or from a checkout of the same revision. Confirm the server and database identity first. From the project root, against the local Compose database:

```sh
umask 077
mkdir -p backups
oq_stamp=$(date -u +%Y%m%dT%H%M%SZ)
uv run python manage.py backup_manifest --operator "A. Operator" \
  --output "backups/qm-lims-${oq_stamp}.manifest.json" \
  --dump "backups/qm-lims-${oq_stamp}.dump"
```

The command opens one read-only snapshot, runs `pg_dump --format=custom --no-owner --no-acl` from it and records, for the same instant: each table's row count and a SHA-256 fingerprint of its rows; the columns, constraints, indexes, triggers and functions; the applied migrations; the sequence positions; and the archive's SHA-256 and size. It also checks the evidence the database holds (the `signatures`, `certificates`, `raw data files` and `triggers enabled` checks below). If one fails, it still writes the manifest and exits nonzero: keep that backup and investigate. It never overwrites a file, removes the partial archive when `pg_dump` fails, and creates both files readable by their owner only. `pg_dump` must be of the server's major version or newer (`--pg-dump` names another one). It writes into the archive file the command has already created, through the open file rather than its name, so a name replaced meanwhile cannot send the archive elsewhere; the run is then refused and nothing is kept. It reaches the database as the application does: libpq settings of the environment such as `PGSSLMODE` apply to it, and the password goes through its environment, never the command line. A connection that needs another secret, such as `sslpassword`, is refused with `--dump`. Record the manifest's SHA-256, which the command prints, in the backup log.

Without `--dump` the command writes only the manifest; `--output -` writes it to standard output and the summary to standard error. Use that beside an archive made another way, such as a Render export, taken while nothing writes to the database. Otherwise the archive and the manifest describe different moments, and the restore check reports the tables that changed in between.

The manifest holds counts, hashes and schema definitions, not record content or credentials. The archive holds everything, including account records, PIN and password hashes and sessions, even for a synthetic instance. Keep it restricted and transfer it, with its manifest, to the approved encrypted backup destination; an ignored local directory is not encryption or off-machine protection. Keep a source revision and configuration record beside them, without secret values. The `--no-owner --no-acl` choice means role ownership and grants must be re-established explicitly at restoration.

## Restore check in a new local database

Use an archive created by a trusted operator, and a server of the same PostgreSQL major version as the source: a newer version describes some schema objects differently, and the comparison then fails. Restoration executes database code from the archive, so review provenance and do not restore untrusted uploads. Restore into a **new, isolated database**; do not point these commands at `open_qual`, an active test database or any deployed database. Full schema/data restoration reinstates constraints and triggers; do not pre-run Django migrations into the empty target. `--single-transaction` makes `pg_restore` stop at the first error and keep nothing of a partial restore. [PostgreSQL 17 pg_restore documentation](https://www.postgresql.org/docs/17/app-pgrestore.html), accessed 2026-11-10.

In the same shell as the backup example, or after setting `oq_stamp` to the selected backup:

```sh
oq_restore_db="oq_restore_$(date -u +%Y%m%d_%H%M%S)"
docker compose exec -T db createdb -U open_qual --template=template0 "$oq_restore_db"
```

Continue only if creation succeeds; an existing target name is a stop condition. Do not overwrite it or add `--clean`/`--create` flags to the restore.

```sh
docker compose exec -T db pg_restore -U open_qual --dbname="$oq_restore_db" \
  --no-owner --no-acl --single-transaction --exit-on-error \
  < "backups/qm-lims-${oq_stamp}.dump"
DEBUG=true DATABASE_URL="postgresql://open_qual:open_qual@127.0.0.1:55433/${oq_restore_db}" \
  uv run python manage.py verify_restore --operator "A. Operator" \
  --manifest "backups/qm-lims-${oq_stamp}.manifest.json" \
  --archive "backups/qm-lims-${oq_stamp}.dump" \
  --report "backups/qm-lims-${oq_stamp}.restore-check.json"
```

The report lists each check with its result:

| Check | Passes when |
|---|---|
| `restored copy` | The database checked is not the one the manifest was taken from: not the same database name and database identifier on the same server (its system identifier). A physical copy or point-in-time recovery of the source keeps all three and is refused as well |
| `archive` | The archive's SHA-256 and size equal the manifest's. *Not checked* when the manifest records no archive or `--archive` is not given |
| `migrations`, `tables` | The same migrations are applied and every table has the same rows and fingerprint; a missing or added table fails |
| `columns`, `constraints`, `indexes`, `triggers`, `functions` | The definitions equal the manifest's. PostgreSQL rewrites an `IN` list over a text column on restore, casting each value in turn instead of the whole list; the two forms compare equal |
| `sequences` | Each sequence will next give a value beyond those its column holds, unless the source's did not either (the sign-in announcement always uses id 1) |
| `signatures` | Each signature's content hashes to its stored content hash, and its audit event names the same signer and record and holds the signed content at the signed revision |
| `certificates` | Each issued certificate version's PDF matches its SHA-256 and size and its evidence snapshot matches its hash; each certificate names its current version's checksums |
| `raw data files` | Each raw-data file's and rehearsal evidence file's bytes match their SHA-256 and size |
| `triggers enabled` | Every history and evidence trigger fires in normal sessions: none is disabled or set to fire only in replica sessions |
| `application` | The release running the check has every migration applied, knows every applied migration and passes its system checks |

The command exits nonzero when a check fails, and the report says which and why (up to 50 problems per check, with the total). The report records the manifest's SHA-256, both databases' identity, the operator, user, host, release revision (`SOURCE_REVISION` or `RENDER_GIT_COMMIT`, when set) and time. Keep it, with the SHA-256 the command prints, as the evidence of the restore test. Run the check before testing a newer release on the copy; then rehearse any new migration with no application connected to the target.

Retain the target for inspection; no cleanup or drop is included here. Do not reuse restored sessions or expose a rehearsal server publicly. Do not run scientific test mutations against restored real records; use an independently created synthetic validation database for destructive or negative tests.

## Integrity acceptance

| Check | Required result | Evidence |
|---|---|---|
| Archive and provenance | Checksum matches the manifest; source database, snapshot time and deployed revision are known | `archive`, `restored copy`; the manifest |
| Schema | Expected migrations applied; restored columns, constraints, indexes, functions and enabled triggers match the source | `migrations`, `columns`, `constraints`, `indexes`, `triggers`, `functions`, `triggers enabled`, `application` |
| Evidence | Every table's rows equal the manifest's; any intentionally older recovery point has a documented reconciliation | `tables`, `sequences` |
| Signature binding | Stored content hashes recompute; signer, record type/ID/revision and linked audit event remain present | `signatures` |
| Stored files | Issued certificates and raw-data files match their checksums | `certificates`, `raw data files` |
| Histories | Audit reviews retain selected events; approved rules, samples/results and signed disposition evidence remain retrievable | `tables`; retrieval by hand on a rehearsal server |
| Application | Matching code passes check/readiness, authorized reads and stored export retrieval; access controls still apply | `application`; readiness, sign-in and a certificate download by hand |
| Operations | Recovery time and lost-work interval measured against approved RTO/RPO; quality owner records acceptance before traffic switch | A rehearsal of recovery from backup with the restore check report attached and accepted by quality ([validation records](#validation-records-of-the-laboratory)) |

A matching hash shows consistency with stored content, not resistance to an administrator rewriting both the data and its hashes. Database owners can disable triggers, so keep runtime privileges distinct from migration and maintenance privileges before production use. Zero signatures is meaningful only for a genuinely unsigned source database. Historical signatures bind historical snapshots; their revision need not equal a record's latest revision.

## Render backup and recovery

The Blueprint names `fresh-coa-lims` and `fresh-coa-lims-db` (database name/user `open_qual`), with database external access closed. Do not change network exposure just to perform a routine export. In the database's **Recovery** page, use **Create export**, then download and protect the archive. Render exports are directory-format `.dir.tar.gz`, not the custom-format local dump above: extract in an isolated restricted directory and give `pg_restore` the extracted directory containing `toc.dat`. Use the same fresh-target and no-overwrite safeguards.

An export is not taken from the manifest's snapshot. Take the manifest in the web service's shell with `python manage.py backup_manifest --output -` (save what it prints) while nothing writes to the database, for example outside working hours, and create the export in the same quiet period. Alternatively run `backup_manifest --dump` in the shell and copy both files off the instance, whose disk is not kept. Then restore the export locally as above and run `verify_restore` with the manifest; without `--archive` the `archive` check reads *not checked*, so record the export's checksum separately.

Paid Render databases provide PITR into a new database instance, allowing validation before switching the web service. Availability depends on the workspace's current recovery window; verify the available point in the dashboard. Managed retention is not the organization's records-retention policy, so retain approved encrypted exports independently. New recovery resources and access changes follow the deployment owner's authorization. [Render recovery and backup procedure](https://render.com/docs/postgresql-backups), accessed 2026-11-10.

For an incident, preserve the original service/database, record the requested recovery time, and restore into a separate instance. Keep it private. Check the recovered instance with matching code. A point-in-time recovery has no manifest of its own moment and is refused by `verify_restore`, so run `backup_manifest --output -` on it for the checks of its stored evidence; a restore of an archive is checked with `verify_restore` and the archive's manifest. Then complete the integrity acceptance, reconcile transactions after the recovery point, and obtain quality-owner acceptance. Switch `DATABASE_URL` only as a coordinated cutover with writers stopped; prevent old and recovered databases from both accepting new scientific records. Keep the previous instance until acceptance and retention decisions are recorded.

## Demonstration deployment from `develop`

The project's synthetic demonstration follows `develop`: the Blueprint sets `branch: develop` and `autoDeployTrigger: checksPass`, so Render deploys a commit only after all of its GitHub checks succeed, and does not deploy a commit with a failed check or with none. Under the workspace's **Wait** overlapping-deploy policy, a deploy triggered while another is running waits for it and only the newest waiting commit is deployed; confirm the policy in the workspace settings. A failed build or pre-deploy leaves the previous version serving. Put `[skip render]` in a commit message to keep that commit from deploying.

Each deploy runs the pre-deploy migration against the demonstration's persistent database. A migration merged to `develop` has therefore been applied; correct it with a new migration, never by editing it. This arrangement suits synthetic data only. A deployment holding controlled records keeps auto-deploy off, tracks a release branch and follows the manual procedure below.

## Demonstration reset

A public demonstration whose accounts are published can return to the seed's state on a schedule. This is for synthetic data only. `reset_demo` empties every application table, including accounts, sessions, signatures, audit history and issued reports, and restarts identifiers. The database triggers that keep history rows from being updated or deleted do not apply to this whole-table erase. That is deliberate, and it is why the command is fenced.

```sh
ALLOW_DEMO_RESET=true python manage.py reset_demo --publish-accounts
```

It asks for confirmation unless `--noinput` is given, never asks for credentials, and refuses before erasing anything unless all of these hold:

| Check | Why |
|---|---|
| `ALLOW_DEMO_RESET=true` in the job's environment | The deployment declares itself a demonstration. `DEBUG` alone is not enough, and a laboratory's deployment never sets it |
| `DEMO_PASSWORD`, `DEMO_PIN`, `DEMO_ADMIN_PASSWORD` and `DEMO_ADMIN_PIN` are set, both PINs have 8–32 digits, and `demo_admin`'s pair differs from the published pair | After a reset `demo_admin` is the only administrator, so nothing published may open it |
| The database is empty, or holds the `demo_admin` account that `seed_demo` created | A laboratory's database is never erased |
| No migration is pending and none is unknown to the release | A job from another release than the web service would seed the wrong schema |
| `--journey` is given only with `DEBUG=true` | The journey's result uses the development-only entry path |

A run has two parts:

1. One transaction erases the tables, creates `demo_admin` (the admin role only, no staff or superuser status) with its private password and PIN, and runs `seed_demo` for the other accounts and the draft rules and catalog/sampling profiles. If any of it fails, the transaction rolls back and nothing changes. Requests that arrive meanwhile wait, then see the fresh demonstration; everyone is signed out.
2. The signed steps follow in transactions of their own, because signing never runs inside an enclosing transaction. With `--publish-accounts` the listed accounts' credentials are locked and the announcement is published, signed by `demo_admin`. With `--journey` the chemical rule is approved and the result awaiting review is created. If a signed step fails, the command fails and says so: the demonstration is seeded but lacks that step until the next run.

`ALLOW_DEMO_RESET=true` also lets `seed_demo` run without `DEBUG`, without `--journey`. `DEMO_RESET_NOTE`, if set, ends the announcement, for example with the time of the reset.

On Render the schedule is `render.demo.yaml`, a Blueprint separate from `render.yaml`. In the workspace that already runs the demonstration from `render.yaml`:

1. Create a new Blueprint from the same repository and branch with **Blueprint Path** `render.demo.yaml`. It adds one paid cron job, `fresh-coa-lims-demo-reset`, and refers to the existing web service and database by name. Render asks once for `DEMO_PASSWORD` and `DEMO_PIN`, which will be public, and `DEMO_ADMIN_PASSWORD` and `DEMO_ADMIN_PIN`, which must differ and stay private.
2. Use **Trigger Run** on the job to reset straight away, or wait for the schedule (every day at 08:00 UTC). Change the time in the file's `schedule` and `DEMO_RESET_NOTE` together.

The first run erases whatever the demonstration holds, including accounts created by hand; afterwards administer it as `demo_admin`. The job follows `develop` with the same trigger as the web service. While a release with a migration is being deployed, a run may refuse until the web service has migrated; the next run succeeds.

Render bills a cron job by the second of running time, with a minimum monthly charge per cron job service, and schedules use UTC. [Render cron jobs](https://render.com/docs/cronjobs), accessed 2026-11-12. `render blueprints validate render.demo.yaml` (CLI 2.36.0) accepted the file against the demonstration's workspace on that date, planning one new service; it creates nothing.

## Manual deployment and migrations

The repository is <https://github.com/openbga/qm-lims>. Keep `SOURCE_CODE_URL` pointing at the source of the deployed version.

1. Select the reviewed commit whose checks all passed. Record its identifier, keep its [validation pack](#validation-pack-of-a-release) and record a verified backup/recovery point. Inspect pending migrations and compatibility with the currently running version.
2. Verify that the OpenBGA QM LIMS web service targets its own database and that auto-deploy remains off. In Render's Manual Deploy menu choose the exact reviewed commit. Avoid “latest” when it may have advanced beyond the tested revision.
3. The configured pre-deploy command is `python manage.py migrate --noinput`. Allow this single serialized migration owner to run; do not launch a second migration from a shell. A failed pre-deploy requires inspection, not bypassing the migration gate.
4. Inspect deploy/migration logs, then verify `/health/`, `/ready/`, login and authorized read/signing flows using controlled synthetic records. Record outcomes and operator/time.
5. If code is rolled back, first verify compatibility with the already-migrated schema. Code rollback does not reverse migrations. For incompatible/destructive changes, use the separately rehearsed recovery plan and reconcile lost work.

Render supports automatic deployment after CI checks, manual deployment of a selected commit and a pre-deploy stage. Current service configuration remains the source of truth. [Render deployment documentation](https://render.com/docs/deploys), accessed 2026-11-12.

For an exceptional operator-run migration, stop competing deployment attempts first, confirm the shell contains the intended application revision and database, and run `python manage.py showmigrations --plan`, then the reviewed `python manage.py migrate --noinput`, followed by `python manage.py migrate --check` and `python manage.py check`. Never run `makemigrations` on a deployed instance or edit historical migrations to resolve a failure. Do not run seed/reset commands during routine deployment.

## Validation pack of a release

Each laboratory validates the system for its own intended use. The validation pack is supplier evidence for that work: it shows which automated tests give evidence for each product requirement and how they ended on one commit. It does not validate the system for a laboratory's intended use, configuration or infrastructure, and it does not state compliance with any regulation.

CI builds a pack for every pull request and every push to `develop`, after the application suite, the browser suite and the container smoke test pass (which also runs the [acceptance journeys](#acceptance-journeys) with the application image), and keeps it as the workflow artifact `validation-pack-<commit>` for 90 days. The `validation-pack` job is a check of the commit like the others: an incomplete pack fails it (and is kept, with its reasons), and the demonstration deploys a `develop` commit only after all of its checks pass. A release merges a `develop` commit into `main` with the same tree, so the pack of a release is the one of that `develop` commit: download it from the commit's `checks` run on `develop` and keep it with the release record before the artifact expires.

| File | Holds |
|---|---|
| `index.html` | Status, commit, test run, each suite's environment and counts, every requirement with its status, and per requirement the tests traced to it with their outcomes and descriptions. Readable offline and printable |
| `requirements.csv`, `traceability.csv` | The same tables for a spreadsheet: one row per requirement; one row per requirement and test |
| `pack.json` | The summary, the tests that failed, did not run or were skipped (with the reason the map allows, or none), and results traced to no requirement |
| `results/application/`, `results/browser/` | Each suite's JUnit file as pytest wrote it, with the commit the tests ran on and whether the checkout had uncommitted changes, recorded when the tests started; and `environment.json`: commit, run, runner, Python, the PostgreSQL server version, every installed package with its version, and Chromium's version for the browser suite |
| `documents/` | `product.md` (the requirements), `regulations.md` (the regulatory rows they cite) and `traceability.toml` (the map from requirements to tests), as of the commit |
| `acceptance/` | The evidence folder of the [acceptance journeys](#acceptance-journeys) run with the application image of the commit, as the command wrote it, with its own `SHA256SUMS` |
| `release-notes.md` | The changelog section of the version in `pyproject.toml`, or the unreleased changes while the changelog has none |
| `SHA256SUMS` | The SHA-256 of every other file. Check with `sha256sum -c SHA256SUMS` |

A requirement **passed** when at least one test traced to it passed, none failed, every traced test ran and none was skipped without a reason the map allows. The pack **passed** only when every requirement and project check passed, no test failed, every result is traced, the tests ran on the commit without uncommitted changes and the acceptance journeys included, if any, passed; otherwise it is **failed** (a test failed) or **incomplete**, and the command exits nonzero. A passing test shows that the behaviour it checks worked as tested; it does not show that the requirement is met in full. The requirement's delivery column states what is not implemented.

The map in `docs/traceability.toml` names, for each requirement in [product.md](product.md#requirements-and-traceability), the test directories, modules or single tests that give evidence for it; a project check that states no product requirement, such as the licence notice, is listed under `[project]`. `[skips]` names the tests that may be skipped where a pack is built, each with the reason; today a test that only writes certificates for a person to look at, and the backup round trip, which needs `pg_dump` of the server's major version or newer and is run with the application image by CI's container smoke job, which the pack's job waits for. The application suite refuses a map in which a requirement has no test, an entry does not exist or a test is not traced (`python scripts/validation_pack.py check` runs the same check).

To produce the pack in the laboratory's own environment, run both suites from a checkout of the release, against its own PostgreSQL server, and build it there:

```sh
export UV_ENV_FILE=.env
uv run pytest -n auto --junitxml=build/validation/application/junit.xml
uv run python scripts/validation_pack.py environment --suite application \
  --command "pytest -n auto" --output build/validation/application/environment.json
uv run --group e2e pytest -c e2e/pytest.ini e2e --junitxml=build/validation/browser/junit.xml
uv run --group e2e python scripts/validation_pack.py environment --suite browser --root e2e \
  --browser --command "pytest -c e2e/pytest.ini e2e" --output build/validation/browser/environment.json
uv run python scripts/validation_pack.py build --results build/validation/application \
  --results build/validation/browser --output build/validation-pack
```

Add `--acceptance <folder>` to include the evidence of an [acceptance journeys](#acceptance-journeys) run of the same commit: the build refuses a folder whose files do not match its `SHA256SUMS` or whose release is another commit.

Each suite's conftest writes the commit into the JUnit file when the tests start. The build refuses a JUnit file without it, results whose environment was recorded at another commit than the tests ran on, results of another commit than the checkout, results of two commits, a suite given twice and an existing output directory. A pack built on, or from tests run on, a checkout with uncommitted changes is incomplete and says so. These tests run against a disposable test database. They do not test the deployment's own configuration, data, rule sets or infrastructure; the laboratory's acceptance of those remains its own work.

## Acceptance journeys

The acceptance journeys run the record paths a laboratory relies on, end to end, with the release it is about to use and in its own environment: its image or installation, its PostgreSQL server and its settings. Each journey works on its own synthetic lot through the same server-side services the pages call, and checks at each step what should happen, including what must be refused:

| Journey | What it does | Refusals it checks |
|---|---|---|
| Passing | Receives a lot, assigns its requirements, samples it, records and submits a conforming assay, has it reviewed, signs the QC disposition, issues the certificate and reads it back; tries to change the stored certificate, a signature and an audit event in the database | An observation without a value; review of one's own result; a review signed with a wrong PIN, whose failed attempt is counted and kept although the review is refused; a disposition by the person who received the lot, who also holds the quality role |
| Failing | Records a failing assay, which opens an investigation; the original is reviewed and assessed, one retest is authorized, recorded and reviewed, the investigation concludes that the failure is confirmed and the lot is rejected on its results with a reference to the quality system | Disposition and rejection while the investigation is open; a second retest beyond the specification's one; invalidating the original when the retest also fails; requirements for the rejected lot, to sample it again |
| Corrected | Corrects a receipt's quantity, then an observation the reviewer returned because it differs from the raw data; releases the lot and issues the certificate with the corrected value | A change to the original observation in the database; a disposition by the receipt's corrector |
| Rejected | Rejects a lot with a discrepancy on receipt before any testing; receives the same delivery twice by mistake and cancels the second lot | Rejection by the person who received it; requirements, a disposition and a certificate for the rejected lot |
| Amended | Releases a lot, issues its certificate and amends it with a reason; version 1 is read back unchanged | An amendment from a stale view of the certificate |

Each journey ends by exporting its lot's record as the auditor, so the evidence holds the record as the journey left it. Before the journeys the run creates eight synthetic accounts and the configuration they use: a rule set, a method, a specification (assay 98.00 to 102.00 %, one retest), a sampling plan and the analyst's qualification for the method, each approved by someone other than its author; the author's own approval of the rule set is refused.

Run it in a new database created for it, migrated to the release, with `SOURCE_REVISION` set to the release's commit (Render sets `RENDER_GIT_COMMIT`):

```sh
psql "$SERVER/postgres" -c 'CREATE DATABASE qm_acceptance_20261117'
DATABASE_URL="$SERVER/qm_acceptance_20261117" python manage.py migrate
DATABASE_URL="$SERVER/qm_acceptance_20261117" SOURCE_REVISION=<commit> \
  python manage.py acceptance_journeys --database qm_acceptance_20261117 \
  --output /evidence/acceptance-20261117 --operator "<name>"
```

The command refuses to run when the database it is connected to is not the one `--database` names, so a run whose `DATABASE_URL` was left at the deployment's own database stops before writing anything, even in a new production database that has no account yet. It also refuses a database that holds any account, one that lacks a migration of the release or holds one the release does not know, and an existing output directory. It commits every record it makes, as the pages do, so it runs only where nothing else is kept: never point it at the laboratory's database or at a copy someone still needs. Drop the database afterwards, or keep it to inspect the records; the accounts' passwords and PINs were random and held in memory during the run, never shown, and only their hashes are stored, so nobody can sign in with them. A run takes about a minute, mostly checking PINs at the deployment's hashing work factor. It exits nonzero when a step failed; a failed step stops its journey and the other journeys still run (a failed configuration step stops them all), and the report is written either way. A run that was interrupted leaves the records it made, so the database then refuses another run: create a new one.

| File | Holds |
|---|---|
| `report.html` | The outcome; the operator, start and end; the application version, release, PostgreSQL server, Python, Django and platform; the synthetic accounts and their roles; each journey's steps with what was expected, what was observed, the outcome and the product requirements it gives evidence for; the files with their checksums; and space for the laboratory's review. Printable |
| `report.json` | The same, for tools (schema `oq.acceptance-journeys/1`) |
| `<journey>/<lot>-record-<time>.zip` | The export of each lot's record as the journey left it, the package the lot page downloads |
| `<journey>/<certificate>-v<n>.pdf` | Each certificate version issued, as stored |
| `SHA256SUMS` | The SHA-256 of every other file. Check with `sha256sum -c SHA256SUMS` |

CI runs the journeys with the application image of every commit in a new database, and the [validation pack](#validation-pack-of-a-release) keeps their evidence under `acceptance/`.

The run is evidence that the release behaves as these journeys expect in the environment it ran in. It uses synthetic configuration: it does not test the laboratory's rule sets, specifications, methods, procedures or intended use, nor the pages in a browser, which the browser suite of the validation pack covers. Assess it as a test tool for the purpose the laboratory uses it for, and record that assessment, the issues found and the conclusion in the report's review section or in the validation report. Run it when accepting a release and in the [upgrade rehearsal](#validation-records-of-the-laboratory), and attach `report.html` and `SHA256SUMS` to the rehearsal record. The same five journeys, performed through the pages with the laboratory's own configuration and each lot's record exported, are a starting point for its own acceptance tests.

## Validation records of the laboratory

The laboratory keeps two kinds of validation record in the system, under **Validation** in the sidebar. Both are recorded by one person and accepted by a different quality person with a signature; neither is ever edited. A record that will not be accepted is withdrawn with a reason and recorded again. They support the laboratory's own validation and periodic evaluation; they do not validate the system and state no compliance.

**Intended use** (`/validation/`). Record it once the laboratory has validated the system for its use, before the system is taken into use, and again whenever a change alters that use: a new assay, a function newly used, another release, a change of owner.

1. Write the laboratory's validation report first, outside the system, with its own risk assessment, the review of the [validation pack](#validation-pack-of-a-release) of the release, the laboratory's own tests of its configuration and the issues found. The system holds the decision, not the report.
2. Approve the configuration the use relies on: rule sets, specifications, methods, sampling plans and stability protocols. Only methods with an approved version in force can be chosen as supported assays.
3. A quality person records the intended use: what the system is used for and what is outside it, the supported assays, the process owner and the system owner, other responsibilities, the validation report with its revision and the known issues and conditions of use.
4. A different quality person reviews the record and accepts it. The signature freezes every approved version in force, the version of each supported assay and the running release, which the deployment states in `SOURCE_REVISION` (Render sets `RENDER_GIT_COMMIT`); without either the release is recorded as not stated. Outside Render, set `SOURCE_REVISION` to the deployed commit, or no change of release can be shown. Accepting supersedes the previous acceptance. The signing page is refused if the configuration, the running release or the current acceptance changed after it was opened: reload it and review again.
5. From then on the intended-use list and the accepted record show what changed since the acceptance: each approved version in force that differs from the frozen one, methods in force that are not supported assays, and a different running release; when either side states no release, the pages say the release was not compared. Assess each change under the laboratory's change control. When a change alters the intended use, record and accept the intended use again. The system holds no work because of these changes.

**Rehearsals** (`/validation/rehearsals/`). Record each rehearsal after it took place, as it happened. Quality or the system administrator (admin role) records it; only the recorder attaches its evidence, and a quality person who did not record it accepts it, whether the criteria were met or not. A rehearsal whose criteria were not met states its issues and actions; record a new rehearsal once they are done.

| Rehearsal of | What to perform | Evidence to attach |
|---|---|---|
| Recovery from backup | Take a backup with `backup_manifest`, restore it into a new database and run `verify_restore` ([backup](#backup-with-a-manifest), [restore check](#restore-check-in-a-new-local-database)); bring the application up on the copy and check sign-in, reading and a certificate download; measure the recovery time and the work that would be lost against the laboratory's RTO and RPO | The restore check report and the manifest (both hold no record content), the times measured |
| Downtime and reconciliation | Follow the laboratory's downtime procedure: work on paper or another approved means while the system is unavailable, then enter or attach those records in the system and reconcile them | The reconciliation record: each record made during the downtime and where it now is in the system |
| Upgrade | On a copy of the production data, apply the new release's migrations with no application connected, compare row counts before and after (the restore check report of the copy and a fresh manifest), run the [acceptance journeys](#acceptance-journeys) with the new release in a new database, and repeat the laboratory's acceptance tests on the new release | Row counts or manifests before and after, the acceptance journeys' `report.html` and `SHA256SUMS`, the laboratory's test results; name the release before and after |

Files are stored unchanged with their SHA-256 and the same size limit as raw-data files; a download checks the checksum again, and the restore check verifies it with the other stored files. Do not attach database archives, credentials or real personal data. How often to rehearse, the RTO and RPO, and which records to reconcile are the laboratory's decisions.

## Single sign-on

Single sign-on uses OpenID Connect with one provider per deployment. Register the site at the provider as a confidential web client using the authorization code flow, with PKCE (S256) allowed, and with exactly this redirect URI: `https://<host>/accounts/login/sso/callback/`, one for each host name people use. Then set:

| Setting | Value |
|---|---|
| `OIDC_ISSUER` | The provider's issuer, exactly as its discovery document at `<issuer>/.well-known/openid-configuration` states it. HTTPS is required (plain HTTP only for `localhost`). Use the issuer of your own tenant: a shared multi-tenant endpoint does not state one issuer, so its discovery document is refused and the provider is reported as unreachable |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | The client's credentials. Keep the secret in the platform's secret store, never in Git; rotate it at the provider and here together |
| `OIDC_PROVIDER_NAME` | The name people recognize, shown as **Sign in with** this name |
| `OIDC_TOKEN_AUTH_METHOD` | `client_secret_basic` (default) or `client_secret_post`, as the provider expects |
| `OIDC_SCOPES` | `openid email profile` by default; `openid` is required. The email, username or name the provider returns is shown on the link so people recognize it; only the issuer and subject identify the person |
| `OIDC_PROMPT` | `login` by default: the provider authenticates the person at every sign-in, so a session someone else left open at the provider on a shared workstation is not used. When the ID token states `auth_time`, a time before the request is refused; a provider that ignores `login` and omits `auth_time` cannot be detected, so confirm the behaviour during your validation. Set `select_account` or leave it empty only if your access procedure accepts that risk, or if the provider refuses `login` |

The ID token must be signed with an asymmetric algorithm (RS256, PS256, ES256, EdDSA and their stronger variants) by a key in the provider's published key set; tokens that also name other clients as audience are refused. The application fetches the discovery document once per process and the key set when a token names a key it has not seen, with a 10-second timeout: allow outbound HTTPS from the application to the provider. The document must name the configured issuer and HTTPS endpoints, and only the issuer, the three endpoints, the signing algorithms and `authorization_response_iss_parameter_supported` are used from it; it must be served at that address without a redirect. After a failure the provider is asked again only after 30 seconds. The checked document is kept until the application restarts: restart it after the provider changes its endpoints or signing algorithms (new signing keys are fetched by themselves). If the provider cannot be reached, sign-in with a password still works.

After a provider or tenant change every existing link stops signing in (the issuer differs): owners unlink and link again on **Organization sign-in**, where the old link is marked as made with another provider. Signing out here does not sign the person out at the provider. The provider's own multi-factor check is not taken in place of a second factor set up here; set `MFA_REQUIRED_ROLES` as your procedure requires. Test the sign-in, a refused sign-in and an unlinked identity with your provider before production use, and keep the evidence with the validation of your configuration.

## Bench checks at result entry

Before a native observation or batch QC result is recorded or corrected, the analyst needs independently approved qualification evidence whose activity matches the method code (case-insensitive). The validity dates must cover the current deployment-local date, approval must already have occurred, and revocation must not have taken effect. A role assignment alone does not satisfy this check. Preserve the referenced training/suitability evidence under the organization's controlled procedure.

The entry also names the instruments and the reagent or standard lots used. Each selected instrument must be in service with an independently accepted calibration that has not expired and, where the equipment requires it, current qualification evidence. Each selected lot and its source lots must be released and unexpired. A method version can require at least one instrument, at least one lot, or both; set this when the version is created, because it cannot be changed on an existing draft. Register equipment, record and accept calibrations and release lots before testing starts, or entries for such methods are refused.

The configured `ANALYTICAL_BENCH` is `config.integrations.LaboratoryBench`; removing the setting holds every observation and batch QC entry. A successful entry freezes the user, activity, qualification, instruments and lots on the result and its audit event, and adds one resource-use row per instrument or lot. A refused entry stores nothing; the refusal is recorded as the audit event `resource.use_blocked`. Correction rechecks the correcting analyst and the resources selected for the correction. Existing evidence is preserved after a later expiry, revocation or failed calibration.

After a failed calibration the equipment is out of service, and its page lists the tests and QC batches that used it since the last accepted passing calibration. The signed return to service records that this list was assessed; deciding what to do about each affected result remains a quality decision outside the software.

The software checks what the analyst selects. It does not know which instrument or lot a method needs, and results recorded before this check existed carry no instrument or lot. Validate these boundaries and failure cases when approving the deployed workflow.

## Contract laboratories

A test can be performed by an outside laboratory instead of at the bench. Quality adds the laboratory to the register under Laboratory, Contract laboratories, and records an approval for each method it may perform: the method code as it appears in the method catalog (matched whatever its case, for every version of the method), a reference to the evidence, and the first and last day it is valid. A second quality person signs the approval; until then nothing is accepted. Evidence whose dates already lie in the past can still be recorded and signed, for reports dated within them. Enter the dates the evidence supports, because an approval can be neither edited nor extended: record a new one for a renewal, and revoke one that should no longer be relied on. The dates are the signer's statement of when the evidence applies, so an approval signed today with an earlier first day covers reports dated from that day. The scope text is shown with every result that relies on the approval and is not checked by the software.

An analyst records the laboratory's report on the open test. The report is accepted when a signed, unrevoked approval for the test's method includes the date printed on the report, and that date cannot be in the future. An approval that has run out since still covers a report dated within it; a revoked approval covers nothing. The analyst needs no qualification for the method, and no instrument, reagent lot or QC batch is recorded, because that work was done by the contract laboratory. Keep its report under document control and enter where it is kept; a copy can be attached to the test as a raw-data file.

A refused report stores nothing and is recorded as the audit event `contract.report_refused` on the analyst's account, with the test, the laboratory, the report number and date and the reason. An accepted one is recorded as `contract_result.recorded` or `contract_result.corrected` on the test, freezes the laboratory, the approval and the report on each observation, and adds one row to the list of results on the laboratory's and the approval's pages. A correction that keeps the laboratory and the report corrects a transcription error on the evidence already relied on; one that names another laboratory or report is a new acceptance and is checked again. After a revocation the list on the approval's page is the set of results to assess. They are not changed or held, the software records no assessment, and the test record, the review page and the disposition page say that the approval was revoked; place a hold from Holds where a lot must wait. The quality agreement, the audit of the laboratory and the transfer of the method to it are outside the software.

## Suppliers and receipt details

A lot is received with its receipt details, so a lot from a supplier needs that supplier on the register first. A quality user adds suppliers under **Suppliers**; a supplier's identity cannot be edited or removed afterwards, so add a new entry when a name or site changes. The register itself records no qualification, and the software does not check a supplier's status at receipt: a lot can be received from any supplier on the register. Whether a supplier's results can be relied on is a separate signed record (see Relying on a supplier's results); keep supplier approval and audits under the organization's own procedure.

Receipt details are corrected only while the lot is in quarantine, by a new record that keeps the one it replaces. A discrepancy recorded on receipt does not hold the lot; place a hold when the lot must not be dispositioned until it is resolved. Lots received before this release have no receipt details. An analyst can record them from the delivery documents while the lot is in quarantine; a lot released earlier stays without them.

For a lot received from a supplier, an analyst can record what the supplier's certificate of analysis states once the lot has approved requirements, from **Record supplier certificate** on the lot record. Each stated result is compared with the lot's specification and kept apart from the laboratory's own tests: recording it answers no requirement, and the tests the lot needs do not change unless a stated result is accepted in place of a test. A result that does not meet the specification is shown on the lot record and on the disposition page and does not hold the lot; place a hold when it must be resolved first. A record made in error is withdrawn, not deleted. The certificate itself is not uploaded: the record names where it is kept. Whoever records, corrects or withdraws a supplier certificate cannot sign that lot's disposition, so have someone other than the quality signer transcribe it.

The demonstration seed adds two synthetic suppliers. On a demonstration with a scheduled reset they appear at the next reset after this release is deployed; until then a quality account adds one.

## Relying on a supplier's results

A result stated on a supplier's certificate can stand in for the laboratory's own test of a lot. Nothing is relied on by default; three signed records are needed.

| Step | Who | Where | What it decides |
|---|---|---|---|
| Allow it in the rule set | Quality authors a new rule set version; a different quality person approves it | **Rule sets** | The policy carries `"supplier_results": {"own_tests": ["identity"]}`. `own_tests` lists the test codes the laboratory always performs itself, each one of the rule set's `required_tests`; list every identity test there. A rule set without `supplier_results` allows no reliance, and lots keep the rule set version they were received under. |
| Qualify the supplier | One quality person records, a different one signs | The supplier's page, **Record qualification** | One supplier, one material, the tests covered, how the supplier's results were confirmed, an evidence reference and a first and last day. It covers lots received between those days. Renewal, a wider scope or a correction is a new qualification. |
| Accept the result on the lot | An analyst proposes; a reviewer who neither proposed it nor recorded the certificate or the lot's receipt details signs | The supplier certificate's page, **Propose in place of a test**, then **Accept** on the record | That one stated result answers its requirement for this lot. |

The certificate record must state the method and the limits beside the result, the stated result must meet the lot's specification, and no other current certificate of the lot may state a failing result for the same test; otherwise the requirement is tested in the laboratory. A requirement the laboratory has started testing (a result, a raw-data file, a QC batch or a decision) cannot be handed to the supplier's result, and a requirement a proposal or acceptance stands for takes no laboratory work until that is withdrawn. **Withdraw** on the record works while the lot is in quarantine: a proposal is withdrawn by an analyst, a reviewer or quality with a reason; an acceptance that was signed is withdrawn by a reviewer or quality with a signature. The lot is still sampled.

An acceptance is not updated when something underneath it changes. If the certificate record is corrected or withdrawn, another certificate recorded for the lot states a failing result for the test, the receipt is corrected to another supplier or another date received, or the lot's requirements are assigned again, the acceptance is shown as no longer standing and blocks the disposition: withdraw it, then propose the result again from the current record or test the requirement.

Revoking a qualification (any quality person, signed) stops further reliance at once; proposals not yet accepted are shown as no longer standing and are withdrawn. Acceptances already signed stay, are named where the disposition is signed and are listed on the qualification. The software records no assessment of them and holds no lot; decide under your procedure whether a lot needs a hold. How often a supplier is confirmed again is yours to set through the last day of each qualification: the software does not count lots, schedule full testing or compare a supplier's results with yours across lots.

A deployment that replaced the testing adapters: `ANALYTICAL_SUPPLIER_RESULTS` names the class the lot gate asks for accepted supplier results (`lot`, `standing`, `standing_by_lot`). Without the setting no supplier result answers a requirement.

## Revising a specification, a method, a sampling plan or a rule set

Create the new version from the document's page, have a different quality person approve it, and give it the period in which it is to apply. If that period overlaps an approved version, the approval retires the earlier one; the approval page lists what the signature retires and when.

| The new version starts | The earlier approved version |
|---|---|
| In the future | Applies until the new version's start |
| In the past or now | Applies until the moment the approval is signed; it is never retired retroactively |
| Before an approved version that has not started yet | That later-starting version never applies |

A draft cannot retire an approved version with a higher number: withdraw the draft and create a new version. A retired version stays readable with its approved content and signature; the version list shows which version replaced it and from when. There is no action that retires a version without approving a successor.

Lots already received keep the versions frozen when their requirements were assigned, so a revised specification, method or sampling plan changes nothing for them by itself. For a method that runs in QC batches, a test joins only a batch of the method version it is frozen to. **New QC batch** therefore offers the version in force and, while open tests not yet in a batch are frozen to an earlier version, that earlier version too ("earlier version, for tests in progress"), so that work a lot has started can be finished and evaluated. The method approval page counts the tests in progress frozen to the version it retires. A lot that has been sampled keeps the sampling plan version its samples were taken under, also when its requirements are assigned again before testing. A revised **rule set** does: tests are assigned and the lot is dispositioned only while the lot's rule version is in force. Results already recorded can still be reviewed and an investigation concluded. Before approving a rule version that takes over at once, look at the count of lots in quarantine on the approval page; either start the new version later, so that lots in progress finish first, or move each of those lots afterwards: assign its requirements again if it has no test yet, replace them with a signature if it has.

## Markets, customers and several sets of requirements on one lot

A lot's requirements are assigned under one or more **scopes**: `general`, and a name the laboratory gives each market or customer whose requirements differ, for example `eu-market`. The scope names are yours; use one spelling everywhere, because a lot is matched to the configuration by the name. The assignment form lists the scopes the configuration uses.

| To require | Configure |
|---|---|
| Other limits, methods or tests for a market or customer | A specification of the material and stage with that scope (Catalog, **New specification**, Scope). It applies in full to every lot assigned under the scope, beside the specifications of the lot's other scopes |
| Tests that must be performed for a market, a customer, a material or a stage, whatever the specification says | A rule set whose policy carries `applies_to`, for example `{"scopes": ["eu-market"]}`, `{"materials": ["mat-001"], "stages": ["incoming"]}`. Each key is a list; a key left out matches every lot; one of the listed scopes is enough. The rule set then applies to every such lot beside the lot's own rule set, from the next time the lot's requirements are assigned or replaced |
| Reliance on a supplier's results under such a rule set | `supplier_results` in that rule set's policy as well: every rule set a lot is under must allow the reliance, and a test any of them lists under `own_tests` stays with the laboratory |

An additional rule set is not offered when a lot is received, and a rule set keeps its kind: create an additional rule set under its own code. Approval refuses a material or stage that does not exist. The site is the deployment; there is no site key.

The lot is placed on an **applicability hold** with the reasons when a named scope has nothing configured, a specification or method has no version in force, or a rule set requires a test that no specification applying to the lot requires. Resolve these in the configuration and assign the requirements again.

When two specifications state the same test differently (limits, method version, rounding, replicates, name or whether it is required), nothing is merged and neither is picked. A quality person who recorded none of the lot's data opens **Sampling**, the lot, **Decide conflicting requirements**, chooses for each such test the requirement that applies to this lot, gives a reason and signs. A lot has to meet every specification that binds it: choose the requirement under which a passing result also meets the others, or record why another specification does not bind this lot. The software does not check the choice. The requirements not chosen stay in the lot's record, are shown where the disposition is signed and are printed on the certificate. Assigning the requirements again asks for the decision again; once quality has decided, only quality assigns them again, and the disposition page names a decision that was set aside this way. Where the same difference returns for every lot, revise the specifications so that they agree, or keep one complete specification for that market or customer and assign such lots under that scope alone.

A requirement chosen before testing can be changed once testing has started only by a signed replacement: quality opens the lot's requirements page and follows the link to review a replacement, chooses the other requirement and signs. The test made under the first choice is then superseded and repeated, and the replacement is refused while an investigation is open on the lot.

Rule set versions end on their effective end date unless a later version is approved. Before an additional rule set that is the only configuration of a scope ends, approve its next version or a specification for that scope: a lot in testing under the scope cannot be dispositioned once the version it froze is no longer in force, and its requirements cannot be replaced while the scope selects nothing.

Upgrading: the migration `sampling.0005` adds columns that the previous release does not read. Inserts of the previous release keep working while a deployment replaces it, but once a lot is assigned under several scopes, falls under an additional rule set or holds a decision, no worker of the previous release may serve the database (it would replace such a lot's requirements under its first scope alone and ignore additional rule sets), and the migration cannot be reversed.

A lot is tested once against the requirement that applies. A result is not evaluated against each differing specification, and a certificate for one customer with only that customer's limits is not produced.

## Replacing a lot's requirements during testing

Before a lot has a test, an analyst or quality assigns its requirements again from the lot's requirements page; no signature is needed. Once a test exists, quality opens **Sampling**, the lot, **Replace requirements**. The page shows the versions in force beside the frozen ones, every requirement that changes and what happens to each test, then asks for a reason and a signature.

| Rule | Detail |
|---|---|
| Who signs | A quality person who recorded none of the lot's receipt, supplier certificate, sampling or test data and proposed no supplier result for it; reviewing a test is not authorship |
| What is frozen | The versions in force for the same material, stage and scopes, the version in force of the lot's own rule set and the additional rule sets that apply then. The sampling plan is kept |
| Requirements stated differently | Where the specifications in force state a test differently, the page lists every statement and asks which one applies; a choice made for the lot's current requirements is carried while its scope still states the test. Nothing is signed while a test waits for a choice |
| Tests that carry over | Those whose requirement is exactly the same: name, acceptance criterion, rounding, replicates and method version |
| Tests that are superseded | Every other test. It is kept with everything recorded on it, takes no more work and never counts. **Assign required tests** on the lot's testing page then adds a linked repeat under the new requirement |
| Refused when | An investigation is open on the lot; a test that would be superseded is open with results or raw-data files that were not submitted (complete and submit it first); nothing changed; no version is in force or the rule set requires a test the specification lacks |
| Supplier results | One accepted or proposed against the replaced requirements stops standing: withdraw it, correct the supplier certificate record so that it is compared with the new requirement, and propose it again |

A recorded result is not evaluated again against revised limits: a test whose requirement changed is repeated. A confirmed out-of-specification result keeps blocking the lot whatever requirements apply later. The software does not decide which lots must move to a new version and records no impact assessment; reference your change record in the reason. If a lot's sampling plan version has reached its own end, a resample for an investigation is refused; there is no path to change the plan of a lot in testing.

A deployment that replaced the testing adapters: `REQUIREMENT_REPLACEMENT_TESTING` names the class that tells the replacement what happens to the lot's tests (`effects`, `lock`, `apply`). Without the setting requirements cannot be replaced once testing has started.

## Stability testing in the system

To test a study's pulls in the system, approve a specification that states the acceptance criterion of every test the protocol names (stage, scope and material as the laboratory decides; it can be the specification used for release) and name it when the protocol is created. The protocol cannot be approved while the version in force of that specification does not state a test of one of its time points, or a method has no version in force. A study of such a protocol starts only on a lot whose assigned requirements are of the specification's material; a lot that has no requirements assigned is refused, because its material is not established.

If a protocol draft cannot be approved because its specification does not state one of its tests (a mistyped code, the wrong specification), withdraw the draft (Withdraw draft, by its author or by quality) and draft the next version of the code. Each pull's tests freeze the specification version in force when the analyst assigns them; a version approved while the Assign tests page is open refuses the assignment and the page shows the criteria in force for review. Approving a later version changes nothing for tests already assigned and applies to later pulls; the study page lists the criterion each result was judged against, so a change between time points is visible. Assign a pull's tests when it is pulled, not in advance.

The tests of a pull never touch the record of the lot: the lot's revision, gates, disposition evidence and certificates do not change, also when a result fails. A failing result opens an investigation that holds only the pull. Decide under your own procedure whether the lot, or other lots, need a hold (Stability, Holds), an extension of the investigation, a recall assessment or a report to an authority; record the impact in the investigation's entries. The software does none of these and starts no clock. A pull is retested on the material pulled; if more material must be taken, record that in the investigation and take it under a new pull of a protocol version that schedules it. A pull that was taken but cannot be tested is recorded as missed with the reason (Mark missed) when nothing of its testing is in progress, it is not ready for acceptance and none of its results failed (a failing result is recorded through the acceptance, or the study is terminated); its reviewed results stay in the record, and the study can then be completed.

Accepting a pull is a reviewer's signature by someone who neither pulled it, linked its evidence nor produced or investigated any of its results. A confirmed failure is accepted with the outcome that the criteria were not met, so the study can still be completed. A study is not closed while testing of its pulls is in progress: a test awaiting review, an open test that holds results or raw data, or an open investigation. A test that only has a place in a QC batch does not count; if that batch is later rejected, the test of a closed or missed pull is left as it is. Finish those first; an open test that holds nothing is left as it is when the study is terminated, and a closed study's pulls take no more testing.

A deployment that replaced the testing adapters: `ANALYTICAL_STABILITY_PULLS` names the class testing asks about pulls (`requirements`, `refusal`, `lock`). Without the setting no pull is tested in the system; pulls still link a sample or external evidence.

## Calculated results

A calculation is approved with the method version: the formula, its named inputs with units, the unit of the result and its decimals. The quality owner who approves the version is approving the formula; verify it against the controlled procedure with worked examples before approval, and again in intended-use validation. The software evaluates the formula exactly as written, carries 50 significant digits and rounds the result half-up to the approved decimals. It does not convert units, apply significant-figure rules or round intermediate values. Changing a formula means a new method version; tests already assigned keep the formula they froze.

## Raw-data files

Raw-data files attached to tests are stored in the PostgreSQL database, so they are included in database backups and count toward database size. `RAW_DATA_MAX_BYTES` sets the largest accepted file (default 10 MiB, at most 50 MiB); a test holds at most 20 files. Files are kept exactly as received and are never opened by the software, which also means they are not scanned for malware: handle downloaded files under the organization's own controls. A file cannot be removed once attached. `RAW_DATA_TOTAL_MAX_BYTES` sets an optional ceiling on all raw-data files and rehearsal evidence files together (0, the default, sets none); once it is reached further files are refused. On a public demonstration set a small file limit and a ceiling, as the demonstration blueprint does. A file above the limit is refused in the browser before it is sent. The server refuses an upload that declares more than the file limit plus 1 MiB with status 413 before reading its body, and closes the connection; a file that is over the limit by less is stopped while it arrives. This relies on the server closing the connection after an unread request, as the Gunicorn command in the image does; a different server or a proxy that buffers uploads may still receive the whole request.

## Accounts, sessions and signing

| Operation | Procedure and boundary |
|---|---|
| Provision | Verify individual identity under the organization's SOP. Use signed **Users and roles**, or audited `create_staff` in the controlled operator shell, with a named administrator and reason; passwords are entered privately. Avoid shared accounts and shared PINs |
| Roles | Use signed **Assign roles** or the audited `assign_roles` operator command; both replace the whole role set. Zero roles revokes laboratory authority. Superuser/admin status is not scientific review authority |
| PIN enrollment/replacement | Owner confirms current login password at `/signature-pin/`; 8–32 digits, Django hash storage and an attributed event. Never retrieve a PIN or reset by editing credential rows |
| Failed signing | Five failed PIN attempts cause a 15-minute signing lock. Review denied-signature events for misuse. Investigate before repeated recovery; do not clear counters through SQL |
| Two-factor sign-in | Each owner sets it up on **Two-factor sign-in** with a security key or passkey, an authenticator app, or both, and keeps the ten recovery codes apart from them. Security keys and passkeys need HTTPS and the site's host name (or `localhost`): they are bound to that name, so keys registered at one host name do not work at another, and none can be used when the site is opened by an IP address. Plan the final host name before people register keys; after a host name change they sign in with the app or a recovery code and register their keys again. The expected origin is the host and scheme each request arrives with, so the reverse proxy must pass the original `Host` and set `X-Forwarded-Proto: https` (as it must for the HTTPS redirect anyway); if keys stop working after a proxy change, every key answer is refused and counted, so check the proxy first. A key that checks its holder's PIN, fingerprint or face also signs in on its own with **Sign in with a passkey** (no password; the PIN is still entered for every signature); set `PASSKEY_SIGN_IN=false` if your access procedure asks for the password every time. Answers refused there are not counted toward the account's lock (a key's signature cannot be guessed, and counting would let anyone who has seen a key's credential ID lock the account); they are logged as `signin.passkey_failed`, so review repeated lines for one account. Each press of **Sign in with a passkey** stores a request in a new session row, so keep the per-address rate limiting at the reverse proxy and run `python manage.py clearsessions` on a schedule. Because a key signs in without the password, changing a password does not end access through a key someone else registered: when an account may be compromised, have the owner check the keys listed on **Two-factor sign-in** (name, added, last used) and remove unknown ones, or reset two-factor sign-in for them. Set `MFA_REQUIRED_ROLES` to the roles your access procedure requires it for (comma-separated, or `all`; empty by default); an account in those roles reaches only the setup page until it has set it up. Changing the setting needs a restart and applies at the next request. For a lost phone without recovery codes, verify the person's identity, then use signed **Reset two-factor sign-in** on their account (another administrator; never your own) or, when no other administrator can sign in, `python manage.py reset_two_factor <username> --actor <administrator> --reason '...'` in the controlled operator shell. The person then signs in with the password and sets it up again. The same reset is the way forward after 100 consecutive wrong codes stop an account's second factor (`account.two_factor_stopped`, and a warning in the application log): treat that as a possible attack on an account whose password is known, and replace the password too. Authenticator keys are stored in the database, as time-based codes require: a backup archive holds them and must be protected like the database itself. For security keys only public keys are stored. A security key whose signature count did not increase is refused and logged as a warning naming the key and account ids (a copy of the key may exist): ask the owner, remove the key, and reset if in doubt |
| Single sign-on | Off unless `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` are all set (setting only some of them stops the application at start). See [Single sign-on](#single-sign-on) for registering the client. Each owner links their account on **Organization sign-in**; an administrator removes a link with signed **Remove organization sign-in link** (another administrator; never your own). Deactivating a person at the provider does not deactivate their laboratory account: deactivate it here too, because the password still signs in. When an account may be compromised, check its link on the account page (label and subject): someone who knew the password could have linked their own organization account. **Force password reset** and **Reset two-factor sign-in** remove the link (so does the `reset_two_factor` command); the owner's own password change keeps it and reminds them of it. Refused answers are logged as `signin.single_sign_on_failed` with a reason (`expired`, `refused` or `account`) and are not counted toward the account's lock. Each press of **Sign in with** the provider's name stores a request in a session row, as passkey sign-in does: keep per-address rate limiting at the reverse proxy and run `python manage.py clearsessions` on a schedule |
| Failed sign-in | Password sign-in, the two-factor code or security key, PIN enrollment, own password change and two-factor changes share one persistent failure counter per account. After `LOGIN_FAILURE_LIMIT` consecutive failures (default 5) password authentication is refused for `LOGIN_LOCK_SECONDS` (default 900), even with the correct password; the lock expires on its own and there is no administrator unlock. Anyone who knows a username can trigger a lock, so add per-address rate limiting at the reverse proxy and review repeated locks |
| Transport and browser policy | With `DEBUG` off: HTTPS redirect, secure cookies and HSTS for one year (`SECURE_HSTS_SECONDS`; lower it while first verifying HTTPS). `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` are opt-in because they affect other hosts. HTML responses carry a same-origin Content-Security-Policy; update it before adding any external script, style or font. The application trusts `X-Forwarded-Proto`, so serve only behind a proxy that overwrites it and never expose the application port directly |
| Error reports | Credential fields (`password*`, `pin`, `otp_code`) are masked in Django error reports. Configure any additional error tracker not to capture request bodies |
| Signing context | Review displayed identity, record revision, meaning and reason. Each HTTP signature requires username and PIN re-entry matching the authenticated individual; the server rechecks state/authority and commits transition/signature/audit atomically |
| Sign-in activity | Every sign-in, failed attempt and sign-out writes one `openbga.signin` line to standard output with the username and the `Rndr-Id` request ID (`-` when absent); so does a password that waits for the second factor (`signin.second_factor_requested`) and each refused code (`signin.second_factor_failed`). A recovery code used to sign in is also an audit event, `account.recovery_code_used`. On Render, search that ID in the HTTP request log (Pro workspaces and higher) to find the client IP. Lines are kept only for the log platform's retention; stream logs to a controlled destination for longer history. Treat usernames and IP addresses as personal data and set a retention period |
| Session expiry | `SESSION_IDLE_SECONDS=900` (15 minutes) and `SESSION_ABSOLUTE_SECONDS=28800` (8 hours) are the defaults; server expiry requires login again. Existing sessions without login clocks are invalidated; confirm the deployed values |
| Suspicious access/revocation | Revoke laboratory roles promptly through the audited service and follow the approved account/session incident process. Account-management changes revoke previous sessions on their next request; deactivate when login and all authenticated read access must be refused |
| Recovery | Identity owner documents verification and authorizes recovery without asking the signer to disclose a secret. Test the actual recovery/session invalidation behavior before production use |

Username-plus-PIN entry, two-factor sign-in and session limits are software controls, not a declaration of Part 11 compliance or of an authenticator assurance level. Codes from an authenticator app are not phishing-resistant; security keys and passkeys are designed to be, as long as the site is served over HTTPS at its own host name. Identity uniqueness, verified identity, controlled sessions, credential safeguards, intended-use validation and applicable certification/procedures remain the organization's responsibility; see [REG-E09–11 in the regulatory matrix](regulations.md). HTTP signing uses the `signature_username` field plus PIN and records authentication context, including login time, without storing a raw session ID. Trusted programmatic service calls are marked as PIN-only service signatures; do not present them as the validated interactive flow. Check the deployed form, middleware and regression tests when changing these controls. Protect HTTPS, trusted origins, secure cookies, time synchronization and operational logs. Never log submitted passwords/PINs or copy session/credential data into incident reports.
