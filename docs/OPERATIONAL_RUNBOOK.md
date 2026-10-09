# Operational installation and recovery

This procedure describes the dedicated customer runtime. Production release is
still gated by the checks below; configuration and local tests do not establish a
successful customer deployment. Commands are operator instructions, not a record
that a deployment or restore has happened.

## Select and retain the installation

An operational database belongs to one stable `SHOREFRONT_INSTALLATION_ID`.
Retain that ID across process restarts, image upgrades and recovery. The runtime
and migration refuse a stored owner mismatch. This check does not inspect a dump
before restoring it, so operators must verify backup provenance and the physical
target before any restore.

Use a separate database, PostgreSQL credentials, Compose project and browser
origin for every customer and for training. Switching `SHOREFRONT_RUNTIME_MODE`
does not convert simulator records into customer facts. Never use demo reset or
scenario controls against a customer database. Only minimal health, runtime
capabilities and account-entry routes are public; customer records require a
session.

Record the exact installation ID, origin, database name/user, physical volume,
Compose project, image tags/digests, source revision and private configuration
location in the operator's installation inventory. Keep secrets outside Git and
outside logs. A restore also recovers account, invitation and session state from
the backup date; review any access revocations that happened after that date.

## Empty local operational installation

Follow the explicit SQLite path, installation ID and bootstrap-token instructions
in [README](../README.md#run-locally). The database begins empty, with no seeded
ports, vessels, weather, outcomes or customer accounts. Launch the browser at
the exact configured origin; `localhost` and `127.0.0.1`, or two different ports,
are different origins for authentication.

The first administrator supplies the private setup token, name, email and a
15–128 character passphrase. Store the passphrase privately. Once setup succeeds,
remove `SHOREFRONT_BOOTSTRAP_TOKEN` from the service configuration and restart the
API. Existing accounts and records remain in the database. On subsequent starts,
use the same database URL and installation ID, with schema verification enabled.

Administrators create one-time invitations in Team. Tokens expire after 24 hours
and are shown once; share the token privately with the named recipient. The app
does not send email. Operators manage records; supervisors can approve decision
packets; viewers cannot write. Administrator membership authority does not grant
supervisor decision approval. Keep at least one verified administrator able to
sign in.

## Correcting a record after a version conflict

Records have an effective time and a recorded time. A scheduled or backdated
revision can be the latest recorded revision without being today's displayed
fact. Refreshing the workspace alone does not necessarily resolve that conflict.

When Save reports that a record changed, the editor keeps your draft. Select
**Review latest version** to inspect the latest payload, source and timestamps.
Review is read-only. **Replace draft with latest version** explicitly discards
your unsaved form values and loads that version; it does not save anything.
Reapply the intended correction, identify its source, and select **Save record**.
A newer concurrent correction can still produce another conflict.

The correction becomes effective now. It does not cancel future scheduled
versions; they remain recorded and can take effect later. References absent from
the current choices remain visible instead of being silently cleared. A link to
a record that is not yet effective will fail server validation when saved now;
deliberately select an effective replacement or clear an optional link only if
that is the intended correction. The editor is not a scheduled-version manager.

## Bootstrap expiry and password recovery

A fresh database gets a 24-hour setup window stored in the database. Restarting
the API does not extend it. Migrating an older operational database that lacks
the expiry field leaves setup expired until a trusted installation operator
explicitly reopens it. A completed installation cannot reopen first-user setup.

For an expired, still-empty installation, obtain the owner's approval through
your established support process, configure a private bootstrap token of at
least 32 characters on the API, and use trusted shell access with the **exact**
customer `DATABASE_URL` and `SHOREFRONT_INSTALLATION_ID`:

```sh
cd apps/api
uv run python -m shorefront_api.product_admin --reopen-setup \
  --reason 'Owner verified through the recorded support procedure'
```

This explicitly opens a new 24-hour window and records the operator's reason.
It does not create an account or send a token. Restart the API if its configured
token changed, complete browser setup, then remove the token again. Do not edit
database ownership or delete existing users to bypass this process.

For an existing active account, verify the account owner's identity out of band
and run the following with the same exact database and installation settings:

```sh
cd apps/api
uv run python -m shorefront_api.product_admin \
  --email verified-owner@example.test \
  --reason 'Account owner verified through the recorded support procedure'
```

The utility prompts twice for a hidden passphrase; never put a password on the
command line. Recovery records an audit event and revokes that account's existing
sessions. It does not reactivate a revoked account or send email. The owner signs
in through the browser after recovery. There is no public password-reset service.

## Customer Compose installation

`docker-compose.prod.yml` alone selects the existing **training** runtime.
Operational customer deployment requires `docker-compose.operational.yml` after
the base file. The operational overlay selects the operational migrator and API,
requires the stable owner/origin and makes API startup verify the schema.

Prepare a private deployment environment file outside the checkout. Required
settings include a URI-safe random `SHOREFRONT_DB_PASSWORD`, the dedicated
`SHOREFRONT_DB_NAME`/`SHOREFRONT_DB_USER`, immutable installation ID, exact HTTPS
origin and image tag. Set `SHOREFRONT_APPROVERS_JSON=[]` to satisfy the inherited
base Compose interpolation; operational membership is managed through accounts.
Set the private bootstrap token only until initial setup is complete. The root
`.env.example` documents shapes and placeholders, not usable customer secrets.

For the supplied TLS overlay also configure `SHOREFRONT_PUBLIC_HTTPS_ORIGIN` to
equal the operational origin, `SHOREFRONT_HTTPS_PORT`, and absolute readable
certificate/key paths. Use a trusted certificate for the customer hostname.
Run from the repository root in Bash, replacing the environment file and project
with the values recorded for this installation:

```sh
customer_compose=(docker compose --env-file /secure/customer.env -p customer-one
  -f docker-compose.prod.yml -f docker-compose.operational.yml
  -f docker-compose.tls.yml)
"${customer_compose[@]}" config -q
```

`config -q` validates interpolation without printing resolved credentials. It
does not prove network, certificate or database health. After reviewing the
target and authorizing installation of the dedicated environment:

```sh
"${customer_compose[@]}" build api web
"${customer_compose[@]}" up -d postgres
"${customer_compose[@]}" run --rm migrate
"${customer_compose[@]}" up -d api web
```

Existing installations additionally require `docker-compose.upgrade.yml` after
the base file and before the operational/TLS overlays, the original project name,
the exact external volume in `SHOREFRONT_EXISTING_PG_VOLUME`, and the existing
database/user. Do not repoint an old training database at a customer runtime.
See [safe rename and upgrade](RENAMING_AND_UPGRADING.md) for physical identity
preservation. Never use `down -v` to upgrade or restore an installation.

A separately managed TLS proxy requires its own reviewed startup and recovery
configuration. The supplied operations scripts know the repository's base,
upgrade, operational and TLS overlays; arbitrary external overlays are not
automatically discovered.

## Backup ownership and restore procedure

Name an installation operator responsible for backup frequency, retention,
encryption, restore authorization and recovery-time/data-loss objectives. The
repository includes user-level health and daily-backup timers, but timer
installation does not define a customer's RTO/RPO, off-site durability or
encryption policy. Backups contain customer records and authentication material;
restrict the directory and transfer them through an approved encrypted channel.
Use a new output filename for each backup because an explicitly chosen existing
output path will be overwritten.

Set these switches **in the invoking shell**. They are not read automatically
from the Compose environment file:

```sh
export SHOREFRONT_ENV_FILE=/secure/customer.env
export SHOREFRONT_COMPOSE_PROJECT=customer-one
export SHOREFRONT_OPERATIONAL=1
export SHOREFRONT_TLS=1
# Only for an existing stack using its explicit external-volume overlay:
# export SHOREFRONT_UPGRADE=1
umask 077
ops/backup-postgres.sh /secure/backups/customer-one-20261004T120000Z.dump
```

The script uses the selected running PostgreSQL container's database/user and
creates a custom-format dump. Record its checksum, backup timestamp, installation
inventory and corresponding application version. A nonempty dump is only a
successful extraction check; prove recoverability with a separately authorized
restore rehearsal on isolated storage. Keep the rehearsal disconnected from
customer traffic and integrations while preserving the stored installation ID.

Before restoring, independently verify the chosen project, physical volume,
database/user, image version, installation ID, dump checksum and expected records.
Keep an independently recoverable backup of the current target. Stop other
writers or schedulers outside this Compose stack and book a maintenance window.
The target PostgreSQL service must already be running. Restore replaces tables
represented in the dump; it is a destructive action and is never an automatic
deployment check.

With the same explicit shell switches as the backup and the reviewed dump path:

```sh
SHOREFRONT_RESTORE_CONFIRM=YES \
  ops/restore-postgres.sh /secure/backups/customer-one-20261004T120000Z.dump
```

Restore refuses to run unless `SHOREFRONT_OPERATIONAL` is explicitly `1` or `0`.
Use `0` only for the isolated training database. `SHOREFRONT_OPERATIONAL=1`
preserves operational mode for migration and restart. `SHOREFRONT_TLS=1`
preserves the supplied TLS overlay for restart. The script validates Compose
configuration first, stops its API/web services, restores with PostgreSQL's
single-transaction and stop-on-error options, runs the selected migrator, then
starts API/web. A restore or migration error leaves API/web stopped. Diagnose
the failure before deciding whether to retry or recover the prior backup.

The operational migrator checks restored installation ownership before schema
changes. An owner mismatch does not restart the app, but the dump has already
been loaded by that stage; this is why provenance and target checks precede
restoration. The script does not authenticate dump provenance or inspect its
runtime automatically. It does not revoke restored sessions. Complete post-restore
access review and verify evidence before reopening customer traffic.

## Explicit training isolation

Training preserves the simulator, fixture adapters and guided story. For local
training use a dedicated path and a different browser origin. From `apps/api`:

```sh
mkdir -p .data/training
DATABASE_URL="sqlite:///$PWD/.data/training/shorefront.db" \
  SHOREFRONT_RUNTIME_MODE=training SHOREFRONT_SCHEMA_MODE=migrate \
  SHOREFRONT_DEMO_CONTROLS=0 \
  uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8101
```

From `apps/web`, start its frontend on a distinct origin:

```sh
SHOREFRONT_API_TARGET=http://127.0.0.1:8101 \
  npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Only enable `SHOREFRONT_DEMO_CONTROLS=1` when this training data is disposable.
Training integration keys, synthetic source health and modeled outcomes never
establish live customer observations. Do not copy operational credentials into
this environment.

## Gates before accepting customer traffic

- PostgreSQL: run the explicit PostgreSQL suite, verify migrations/owner rejection,
  and confirm records, revisions, idempotency and audit integrity across restart.
- Recovery: rehearse the documented backup/restore on isolated storage; verify
  records, audit root, account roles, access revocations and expected recovery time.
- TLS: verify the public hostname and certificate trust/expiry, HTTP redirect,
  exact browser origin, Secure/HttpOnly/SameSite session cookies and CSRF denial.
  The container healthcheck bypasses certificate validation and cannot prove trust.
- Accounts and browser acceptance: bootstrap an empty installation, invite an
  operator, create port/berth/vessel/call records, record an incident/task, update
  it, restart, verify history, then prove viewer denial and revoked access at
  desktop/mobile in both themes.
- Operations: establish monitoring/alert ownership, backup retention, capacity,
  storage-growth controls, maintenance/rollback procedures and real adapter
  contracts. Bound request sizes alone do not provide a storage-retention policy.
- Customer acceptance: validate the actual workflows, source licenses, decisions
  and evidence with the accountable customer team. Claims submission, commercial
  commitments and money movement need their own explicit authority.

Record evidence and remaining gaps for each gate. Do not change a release claim
based only on configuration rendering, mocked operations tests or health status.
