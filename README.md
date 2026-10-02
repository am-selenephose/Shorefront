# Shorefront

Port-call planning and shore operations coordination.

**Shorefront is an active, standalone project.** Its official repository is
[am-selenephos/shorefront](https://github.com/am-selenephos/shorefront).
KRATIA is a separate project; this repository is not an archived KRATIA module.

Shorefront combines an inspectable harbor picture, berth/service scheduling,
disruption scenarios, human-approved recovery proposals and durable evidence.
It is an operational prototype with synthetic fixtures and optional configured
feed adapters—not a certified vessel-control system or a production-ready SaaS.

## Current capabilities

- React workspace with harbor overview, map, berth timeline, resources and service dependencies.
- Synthetic and recorded-fixture data with visible provenance and freshness; optional HTTP feed adapters.
- Modeled berth, tug, pilot, bunker and connectivity disruptions.
- Explainable recovery proposals with human operator authorization, stale-state checks and receipts.
- SQLite/PostgreSQL persistence for snapshots, incidents, events, proposals and scenario evidence.
- Authenticated, vessel-scoped normalized event intake and advisory coordination responses.
- Degraded-connectivity queue/replay modeling and diagnostic metrics.

Coordination is **advisory-only**. No helm, propulsion, machinery or other vessel
actuation is permitted. Integration credentials are not human approval credentials.
Synthetic information is not evidence of a real port operation or commercial deployment.

## Repository layout

```text
apps/api/       FastAPI, shorefront_api, domain model and persistence
apps/web/       React/TypeScript/Vite workspace and browser tests
deploy/         BasicDeploy preparation, boot and bundle scripts
ops/            Explicitly targeted PostgreSQL backup/restore scripts
docs/           Architecture, wire boundary and migration notes
```

## Run locally

Prerequisites: Python 3.11+, uv, Node.js 24 and npm. PostgreSQL is optional for
local development; SQLite is the default. Use isolated demo data and loopback
listeners. No live credentials or port services are necessary.

API, in one terminal:

```sh
cd apps/api
uv sync --frozen --extra dev
uv run uvicorn shorefront_api.main:app --host 127.0.0.1 --port 8100
```

Frontend, in another:

```sh
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

Open the local address printed by Vite. The frontend proxies the API to
`http://127.0.0.1:8100`; override with `SHOREFRONT_API_TARGET` if needed.
Starting the API from `apps/api` uses `apps/api/.data/shorefront.db` on a fresh
install. `DATABASE_URL` always takes precedence.

The app does not automatically read the root `.env` for direct API startup.
Supply runtime settings through the process environment or uvicorn's explicit
`--env-file` option. `.env.example` documents configuration shapes, not usable
production credentials. Do not commit real credentials.

To approve a recovery proposal, configure `SHOREFRONT_APPROVERS_JSON` with a
SHA-256 token digest and the operator's identity/role, then use the matching
token in the operator session. Machine integrations have a separate
`SHOREFRONT_INTEGRATIONS_JSON` credential and vessel allowlist. Example digests
are placeholders, not shared login credentials.

## Upgrading an existing installation

**Read [Renaming and upgrading](docs/RENAMING_AND_UPGRADING.md) before restarting
an existing stack.** The repository/folder rename must not select an empty
database or new Compose volume.

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
```

Browser tests use local API/web servers, test-only credentials and `/usr/bin/chromium`.
They do not use a live port service. Test data is created under temporary directories.
See [identity migration verification](docs/IDENTITY_MIGRATION_VERIFICATION.md)
for this change's exact results and unverified gates.

## Product and visual status

The source identity is Shorefront. The high-end colour/UI redesign is a separate
workstream: the prior copper/ivory/espresso palette is reserved for KRATIA;
Shorefront's proposed mineral-white / tidal-green direction has not been applied.
The current UI retains its existing layout and colours during this migration.

Before commercial use, resolve the known authorization/demo-reset,
transaction/atomicity and replay concerns, then prove tenant boundaries,
operational recovery, real integrations and the complete browser experience.
See [next work](docs/NEXT.md). Do not infer production readiness from a passing
identity-migration test suite.

## Documentation and provenance

- [Architecture](docs/ARCHITECTURE.md)
- [Vessel-runtime boundary and frozen v1 contracts](docs/VESSEL_RUNTIME_BOUNDARY.md)
- [Safe rename/upgrade procedure](docs/RENAMING_AND_UPGRADING.md)
- [Original pre-rename README](docs/HISTORY_PRE_SHOREFRONT.md) — retained verbatim as historical provenance. Its archived/moved-to-KRATIA statements and old deployment links are not current instructions.

The Shorefront name is the owner's product decision. This repository change is
not trademark, company-name or domain clearance.
