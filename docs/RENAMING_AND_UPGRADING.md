# Shorefront identity migration

Shorefront is the current standalone product, with its own identity and roadmap.
This is a source and packaging migration, not a database migration or deployment.

## What changed

- Repository: `am-selenephos/shorefront`.
- Python package/module: `shorefront-api` / `shorefront_api`.
- Frontend package: `shorefront-web`.
- Current UI, OpenAPI title, new synthetic provider labels and setup examples use Shorefront.
- New browser session key: `shorefront.operator_token`. The old key is cleared, not adopted. Operators sign in again; credentials themselves are not rotated.
- New runtime keys use `SHOREFRONT_*`. API settings and documented Compose/shell configuration accept their `PORTFLOW_*` predecessors during migration. A present canonical value wins, **including an empty value**. Invalid canonical authorization fails validation; it never falls back to old authority.
- Fresh SQLite default: `.data/shorefront.db`. If only `.data/portflow.db` exists, it is reused in place. Both present is an error requiring `DATABASE_URL`. No bytes are rewritten or files moved by this selection.

## Technical compatibility exceptions

These strings are intentionally retained. They are not current product branding:

| Identifier | Reason |
| --- | --- |
| `portflow.vessel-event.v1` | Published input envelope and historical event payloads |
| `portflow.vessel-event-receipt.v1` | Existing sender receipt contract |
| `portflow.coordination.v1` | Existing advisory coordination consumer contract |
| `portflow-evidence-v1` | Existing evidence-pack format |
| `portflow_accepts_normalized_events_only` | Published invariant response key |
| `portflow_*` metric series | Existing monitoring dashboards and alerts |
| `PORTFLOW_*` aliases | Existing runtime and deployment configuration |
| `portflow.operator_token` | Removal of the retired browser key only |
| Old database/user/schema/volume and saved provider names | Existing physical state and historical provenance |

Do not replace strings in stored evidence, event envelopes, receipts or scenario records: their hashes and history must stay truthful. Fresh synthetic display names change; restored historical records do not. Replacing protocol IDs requires a separate versioned consumer migration.

## Local development

For the existing training runtime, use `uv sync --frozen --extra dev` in `apps/api`
and launch `SHOREFRONT_RUNTIME_MODE=training uv run uvicorn shorefront_api.main:app --port 8100`
from that directory. Direct startup now defaults to the separate operational
runtime; its owner/origin and dedicated database instructions are in the
[operational runbook](OPERATIONAL_RUNBOOK.md).
Relative `.data` is relative to the startup working directory, not the checkout root.
When moving an existing installation to a new directory, set `DATABASE_URL` to the
absolute existing database path or set `SHOREFRONT_DATA_DIR` explicitly. The resolver
cannot find databases in unrelated folders and must not search your filesystem.

Update service managers, scripts and editor launch configurations to the new Python
entrypoint. No compatibility import shim for `portflow_api` is shipped.

## PostgreSQL / Docker upgrade: do not use fresh-install defaults

Changing the checkout directory changes Compose's inferred project name. Changing
volume keys can select empty storage. Changing `POSTGRES_DB`/`POSTGRES_USER` does not
rename an existing PostgreSQL database/user. Therefore an existing deployment must:

1. Record its actual Compose project, PostgreSQL volume, database/user, image IDs,
   credentials configuration and external integrations before changing anything.
2. Create and verify a backup using the **existing running deployment**. Test recovery
   separately in an isolated environment before authorizing a production cutover.
3. Keep the existing database/user values (historically `portflow`, but inspect rather
   than assume) in `SHOREFRONT_DB_NAME` and `SHOREFRONT_DB_USER`. Set
   `SHOREFRONT_EXISTING_PG_VOLUME` to the exact existing physical volume name.
4. Use `docker-compose.prod.yml` **and** `docker-compose.upgrade.yml`, plus
   `-p <existing-project>`. The upgrade overlay requires those explicit identities
   and declares the volume external: a missing volume cannot be silently created.
5. Review `docker compose ... config --quiet`. Full config output contains resolved
   secrets; do not paste or publish it. Build the new images and plan the maintenance
   window without starting a second stack against shared state.
6. During a separately authorized cutover, stop old application workers, switch the
   source/image references, run the migration gate against the selected existing
   database, then verify `/readyz`, stored event/receipt counts, operator roles,
   idempotent vessel replay, and monitoring. A successful health check alone is not
   proof that the correct historical database was selected.

The source change does not execute these steps for you. Never run `down -v` for a
rename. Do not rename volumes or destroy the old checkout until rollback is verified.

Backup/restore scripts accept `SHOREFRONT_ENV_FILE` and
`SHOREFRONT_COMPOSE_PROJECT` (legacy counterparts are fallback aliases). For an
upgrade stack set **in the invoking shell** `SHOREFRONT_UPGRADE=1` and the existing
Compose project; this adds the external-volume overlay. Script switches are shell
variables, not values automatically read from a Compose .env file. Database/user
selection comes from the running postgres container's environment.

Restore remains destructive and requires `SHOREFRONT_RESTORE_CONFIRM=YES` (or its
legacy counterpart). It also requires explicit `SHOREFRONT_OPERATIONAL=0` for the
existing training stack or `=1` for an operational customer stack. Backup/restore
add the operational overlay when this switch is `1`, and preserve the supplied
TLS overlay when `SHOREFRONT_TLS=1` is set in the invoking shell. No restore is
part of this rename. Follow the [operational runbook](OPERATIONAL_RUNBOOK.md) for
current preflight, restore transaction, failure handling and recovery verification.

Use a URI-safe database password for the existing interpolated Compose URL format,
or adapt the deployment connection settings with proper URL encoding before use.
This rename does not introduce a new secret-management system.

## BasicDeploy

Bundles now extract under `shorefront/` and expect `/workspace/shorefront`.
`SHOREFRONT_ROOT` can select another deployment root in the boot script. Preparation
expects the standard bundle location. Point the deployment's boot hook at the new
bundle during an authorized cutover; do not leave an old and new worker running.

**Schema must be explicit.** Set `SHOREFRONT_DB_SCHEMA` to the existing schema for
upgrades (historically `portflow_portfolio`). `PORTFLOW_DB_SCHEMA` is accepted if
the canonical key is absent. There is no default that silently creates a new schema.
Fresh installs may explicitly choose `shorefront`. Schema names are validated before
installation or database access. Read-only schema-configuration check:

```sh
SHOREFRONT_DB_SCHEMA=shorefront SHOREFRONT_BOOT_PREFLIGHT_ONLY=1 sh deploy/basicdeploy_boot.sh
```

This checks configuration syntax only, not connectivity, authorization, deployment
ownership or the existence of data. The new boot lock does not replace stopping the
old process; deployment coordination is still required.

## Rollback boundaries

Keep the previous image/checkout and backup. This rename does not change schema
version 3 or stored wire formats, but verify rollback against a copy of your data;
do not assume that concurrent writes or later application changes are reversible.
To use the old code, restore its entrypoint/configuration and select the same
physical database. Repository URL changes alone do not roll back running services.

## UI and release boundaries

The original source rename was separate from the subsequent visual changes.
The current workspace uses the approved cream-first coastal palette, local Space
Grotesk/Space Mono fonts and an optional dark theme; see [brand.md](../brand.md).
Shared demo mutations now require explicit `SHOREFRONT_DEMO_CONTROLS=1` opt-in.
The isolated guided story does not require that opt-in and does not change the
operational store. Full authorization, transaction/atomicity and real downstream
replay acknowledgements remain production gates, not benefits implied by a rename.
No source rename constitutes trademark or domain clearance.
