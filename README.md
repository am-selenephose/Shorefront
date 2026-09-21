# PortFlow

PortFlow is a port-call operations control tower for live vessel, berth, weather, incident, delay, connectivity, and schedule state.

## Status

Private portfolio build, v0.2 operational core.

## Product principles

- Operational software first, AI/ML as bounded capabilities.
- Real-time state must remain inspectable and attributable.
- Synthetic demo data must never be presented as real port operations.
- Degraded connectivity is a first-class operating mode.
- Port-call dependencies are modeled explicitly, not hidden behind chat.
- Scenario effects must propagate mechanically through schedule state.
- Operational history must survive restart.

## Monorepo

- apps/api: FastAPI service, simulator, persistence layer, event ledger, incident engine
- apps/web: React + TypeScript operations console
- docker-compose.yml: PostgreSQL development service

## Demo domain

The demo uses a fictionalized Rotterdam-like topology and fully synthetic operational data.

Current modeled vessels include MSC Aurora, Maersk Lima, Ever Glory, Nordic Atlas, Seaway Polaris, and Ocean Nova. Names and IMO values are synthetic demonstration data.

## v0.2 proof

### Durable state

- SQLAlchemy-backed canonical snapshot persistence
- SQLite default for zero-config local use
- PostgreSQL support through DATABASE_URL
- append-only operations event ledger
- persistent incident history
- restart restoration of port-call schedule, incidents, risk, and connectivity state

PostgreSQL persistence has been runtime-tested against the included Postgres 17 container.

### Incident propagation

Available deterministic scenarios:

- pilot boarding delay
- tug unavailable
- berth occupation overrun
- high-wind pilot/tug restriction
- control-center connectivity loss

Example demo:

pc-glory berth overrun +90 min -> B07 occupation extends -> pc-nova overlaps -> 55-minute mechanical berth conflict -> both calls become risk-scored from the updated schedule.

### Scheduling and risk

- mechanical berth conflict detection
- dependency-order validation
- explainable risk scoring
- modeled cost exposure
- 16-hour berth Gantt
- conflict highlighting
- port-call stage timeline
- weather/tide restrictions

### Connectivity

Modes:

FULL -> DEGRADED -> CRITICAL -> OFFLINE_EDGE

Loss of transport does not imply loss of local operational state. Offline-edge mode accumulates queued events for future replay work.

## Run

### API with zero-config SQLite persistence

    cd apps/api
    uv sync --extra dev
    uv run uvicorn portflow_api.main:app --reload --port 8100

### API with PostgreSQL

    sudo docker compose up -d postgres
    cd apps/api
    DATABASE_URL=postgresql+psycopg://portflow:portflow-dev-only@127.0.0.1:55432/portflow uv run uvicorn portflow_api.main:app --reload --port 8100

### Web

    cd apps/web
    npm install
    npm run dev

Open http://localhost:5173.

## Verification

    cd apps/api
    uv run pytest -q

    cd ../web
    npm run build
    npm audit --omit=dev --audit-level=high

Current local verification target:

- 12 backend/domain/API/storage tests
- production web build
- zero production npm vulnerabilities

GitHub Actions workflow is committed. The linked GitHub account currently has Actions disabled at account level, so local verification is the canonical proof until that account setting changes.

## API highlights

- GET /healthz
- GET /api/v1/harbor
- GET /api/v1/events
- GET /api/v1/incidents
- POST /api/v1/incidents
- PATCH /api/v1/incidents/{incident_id}/resolve
- GET /api/v1/berth-conflicts
- GET /api/v1/port-calls/{call_id}/risk
- POST /api/v1/connectivity
- POST /api/v1/demo/reset
- WS /ws/harbor

## Next engineering milestone

- idempotent offline event spool and replay
- durable action receipts
- berth rescheduling proposal engine
- service dependencies such as pilots, tugs, cranes, bunkers, customs
- deterministic scenario fixture packs
- browser E2E tests
- API/web containerization
- deployment
