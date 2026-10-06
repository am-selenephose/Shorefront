# Shorefront

Port-call planning and shore operations coordination.

**Shorefront is an active, standalone project.** Its official repository is
[am-selenephos/shorefront](https://github.com/am-selenephos/shorefront).
This repository owns its product, runtime and release lifecycle independently.

Shorefront provides a dedicated operational workspace for customer records,
coordination, evidence-bound decisions and observed outcomes. New direct API
startups default to `operational`: an empty installation with accounts and no
synthetic harbor history. The existing harbor simulator remains available through
explicit `training` mode on a separate database and browser origin.

This is an actively developed operational product. Production deployment,
customer acceptance and recovery gates remain open; the runtime reports
`production_ready: false`. Shorefront does not control vessels or confer legal
authority.

## Current capabilities

- Administrator onboarding, team invitations and administrator/operator/supervisor/viewer roles.
- Server-side sessions, exact-origin and CSRF checks, revocation and installation ownership checks.
- Typed ports, berths, vessels, calls, resources, incidents and tasks with revisions and source attribution.
- Commitments, recipient-acknowledged handoffs and obligations with controlled transitions.
- Evidence-bound decision packets, supervisor approval and recorded outcomes without invented savings.
- SQLite/PostgreSQL persistence, transactional commands, idempotency and stale-revision rejection.
- Effective-time and knowledge-time history with inspectable audit evidence.
- A separately selected training simulator with harbor maps, schedules, modeled disruptions,
  synthetic/recorded fixtures, recovery proposals and advisory integration experiments.

Coordination is **advisory-only**. No helm, propulsion, machinery or other vessel
actuation is permitted. Integration credentials are not human approval credentials.
Synthetic information is not evidence of a real port operation or commercial deployment.

The browser selects the server-declared runtime. Operational mode begins with
setup or sign-in, followed by Pulse, Records, Plan, Evidence and Team.
A failed API connection shows an error and retry; it does not select a demo.
The training runtime retains its guided story and advanced control tower. Shared
training mutations require `SHOREFRONT_DEMO_CONTROLS=1` on disposable data only.

## Repository layout

```text
apps/api/       FastAPI, shorefront_api, domain model and persistence
apps/web/       React/TypeScript/Vite workspace and browser tests
deploy/         BasicDeploy preparation, boot and bundle scripts
ops/            Explicitly targeted PostgreSQL backup/restore scripts
docs/           Architecture, wire boundary and migration notes
```

## Run locally

Prerequisites: Python 3.11+, uv, Node.js 24 and npm. The following creates a local
operational database. Keep its installation ID stable on subsequent starts.
Generate and retain a private random bootstrap token of at least 32 characters
in your password manager before the first launch; enter it at the hidden prompt.

API, in one terminal:

```sh
cd apps/api
uv sync --frozen --extra dev
mkdir -p .data/operational
export DATABASE_URL="sqlite:///$PWD/.data/operational/shorefront.db"
export SHOREFRONT_RUNTIME_MODE=operational
export SHOREFRONT_INSTALLATION_ID=shorefront-local-01
export SHOREFRONT_ORIGIN=http://127.0.0.1:5173
read -r -s -p 'Private bootstrap token: ' SHOREFRONT_BOOTSTRAP_TOKEN
printf '\n'
export SHOREFRONT_BOOTSTRAP_TOKEN
uv run python -m shorefront_api.migrate
export SHOREFRONT_SCHEMA_MODE=verify
uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8100
```

Frontend, in another:

```sh
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`, use the private bootstrap token to create the first
administrator, then remove the token from the API environment and restart it.
Subsequent access uses account sign-in. See the
[operational runbook](docs/OPERATIONAL_RUNBOOK.md) for bootstrap expiry, account
recovery, customer deployment and backup/restore procedures.

The frontend proxies the API to
`http://127.0.0.1:8100`; override with `SHOREFRONT_API_TARGET` if needed.
The explicit URL above avoids selecting a legacy simulator database. Without an
explicit URL, database discovery still supports `.data/shorefront.db` and the
legacy filename documented in [Renaming and upgrading](docs/RENAMING_AND_UPGRADING.md).
Changing runtime mode does not convert their data.

The app does not automatically read the root `.env` for direct API startup.
Supply runtime settings through the process environment or uvicorn's explicit
`--env-file` option. `.env.example` documents configuration shapes, not usable
production credentials. Do not commit real credentials.

For training, explicitly set `SHOREFRONT_RUNTIME_MODE=training` with a dedicated
SQLite path or PostgreSQL database/user and a separate browser origin. The legacy
`SHOREFRONT_APPROVERS_JSON` and `SHOREFRONT_INTEGRATIONS_JSON` settings belong to
training recovery/integration experiments; operational accounts use invitations
and session cookies. Follow the isolated training example in the runbook.

## Upgrading an existing installation

**Read [Renaming and upgrading](docs/RENAMING_AND_UPGRADING.md) before restarting
an existing stack.** The repository/folder rename must not select an empty
database or new Compose volume.

For current operational startup and restore commands, use the
[operational runbook](docs/OPERATIONAL_RUNBOOK.md). The base production Compose
file deliberately selects `training`; customer deployments must also use
`docker-compose.operational.yml`. Retain the existing installation ID and exact
physical database identity across operational upgrades.

- Existing SQLite files are reused in place; ambiguous old/new files require an explicit URL.
- Existing PostgreSQL upgrades use `docker-compose.upgrade.yml`, the exact existing external volume, existing DB/user, and the original Compose project name.
- BasicDeploy requires an explicitly selected database schema; no silent schema rename occurs.
- Old runtime environment keys remain compatibility aliases. Explicit new values win, including empty values.
- Published v1 protocol IDs, evidence formats and metric series retain their technical names to avoid breaking current consumers.
- Browser sessions require reauthentication under the new product identity.

The Compose files are **deployment-shaped scaffolding**, not evidence that the
commercial release gates have passed. This repository rename does not deploy,
move data, rotate secrets, publish images or grant production access.

## Verify

```sh
cd apps/api
uv run pytest -q
```

Deployment tests render Compose configuration without starting containers.
They require Docker Compose CLI; they are skipped if Docker is absent. Boot
preflight and backup command tests use isolated test fixtures, not real services.

```sh
cd apps/web
npm run typecheck
npm run test:config
npm run build
npm run test:e2e
npm run test:product
```

Browser tests use local API/web servers, test-only credentials and `/usr/bin/chromium`.
They do not use a live port service. Test data is created under temporary directories.
See [identity migration verification](docs/IDENTITY_MIGRATION_VERIFICATION.md)
for this change's exact results and unverified gates.

## Product and visual status

The source identity is Shorefront. Its owner-selected coastal palette is applied
to the workspace, controls, status surfaces and map markers: a pale-cream base,
deep blue-green text, muted teal structure, warm yellow and peach accents.
The header's **Dark mode** switch offers inverse contrast: deep blue-green
surfaces, cream text, teal structure and the same warm accents. Cream stays the
default; an explicit selection persists locally across refreshes. The previous
dark-first default was replaced, not restored. See [brand.md](brand.md) for exact
sampled colours, semantic roles and contrast rules. This replaces the earlier
unapproved Tidal Jade proposal. Other projects' visual identities are not reused.
Locally bundled Space Grotesk and Space Mono replace the old typography. The
existing workflows have a lighter layout, larger operational type, readable
timeline lanes and smaller-screen navigation. Wider commercial product work
remains open. See [cream workspace verification](docs/CREAM_WORKSPACE_VERIFICATION.md)
for the earlier checkpoint, and [theme-switch verification](docs/THEME_SWITCH_VERIFICATION.md)
for current browser checks, screenshots and remaining limits.

The operational workspace serializes writes through database transactions and
checks installation ownership. This does not establish high availability,
customer deployment readiness or real integration acceptance. Before commercial
use, complete the customer-specific TLS, PostgreSQL, backup/restore, monitoring,
storage growth, browser and operational acceptance gates in the runbook.
The training runtime retains its narrower single-process coordination boundary.

## Documentation and provenance

- [Architecture](docs/ARCHITECTURE.md)
- [Operational installation, accounts and recovery](docs/OPERATIONAL_RUNBOOK.md)
- [Operational product design](docs/superpowers/specs/2026-10-04-operational-product-design.md)
- [Decision-workspace verification](docs/DECISION_WORKSPACE_VERIFICATION.md)
- [Atomic-command verification](docs/ATOMIC_COMMAND_VERIFICATION.md)
- [Vessel-runtime boundary and frozen v1 contracts](docs/VESSEL_RUNTIME_BOUNDARY.md)
- [Safe rename/upgrade procedure](docs/RENAMING_AND_UPGRADING.md)
- [Historical source record](docs/HISTORY_PRE_SHOREFRONT.md) — retained as provenance, not current branding, architecture or deployment instructions.

The Shorefront name is the owner's product decision. This repository change is
not trademark, company-name or domain clearance.
## Operational connections

The administrator-only Connections workspace provides two deliberately different external boundaries.

Inbound machine sources receive a one-time bearer credential and an explicit allowlist of operational record kinds they may write through POST /api/v1/integrations/{source_id}/records. Accepted records remain ordinary versioned Shorefront facts and are attributed to integration:<source_id>. Batches are bounded, atomic and idempotent.

Partner projections receive separate one-time bearer credentials and explicit record-kind and payload-field allowlists through GET /api/v1/partner/projection. A projection may optionally be scoped to recorded port calls and their direct operational context. Raw source attribution, actor IDs and fields outside the allowlist are not returned.

These are Shorefront-scoped API credentials, not federated SSO, vendor-specific AIS/TOS/weather connectors, a standards schema registry, contractual authority or evidence that an external provider accepted the integration. Real provider entitlements and delivery contracts remain separate release work.
