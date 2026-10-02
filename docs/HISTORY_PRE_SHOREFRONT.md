# Archived — PortFlow moved into KRATIA

PortFlow is now maintained as the shore/port service inside the canonical **KRATIA** monorepo:

https://github.com/am-selenephos/KRATIA

Canonical path:
`apps/portflow/`

This standalone repository is preserved read-only for historical tags, branches, release provenance, and migration traceability. New development belongs in KRATIA.

---

# KRATIA Maritime — Shore Coordination

> Public product surface: **KRATIA Shore**. Internal service names, environment
> variables and portflow.* integration contracts remain stable for
> compatibility.

## v0.17.0 — KRATIA Shore public product UI

The shore product surface now carries the KRATIA Maritime identity while
preserving the existing PortFlow engine and wire compatibility.

Visible operator changes:
- KRATIA / MARITIME · SHORE brand shell;
- KRATIA Shore operations-control-tower title;
- explicit authority strip for shore coordination, privacy-minimized vessel
  events, human approval and NO VESSEL ACTUATION;
- existing vessel-exception provenance/resolution UI remains intact;
- browser and OpenAPI titles now identify the public module as KRATIA Shore.

This is a public-product/UI rename, not a protocol migration. Existing
portflow.* contracts, API paths, environment variables, persistence schema and
integration credentials remain stable.

PortFlow is a port-call operations control tower for continuously updated vessel, berth, weather, incident, delay, connectivity, and schedule state.

## Status

Private portfolio build, v0.16.1 vessel-exception hardening patch on top of the completed v0.16 worker-to-shore integration.

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

### Production-shaped container stack

The production-shaped stack runs Postgres, FastAPI, and Nginx/React behind one web origin.

    cp .env.example .env
    # set a strong PORTFLOW_DB_PASSWORD in .env
    sudo docker compose -f docker-compose.prod.yml up -d --build

Default external HTTP port is 8088 and can be changed with PORTFLOW_HTTP_PORT.

The production compose intentionally requires PORTFLOW_DB_PASSWORD instead of shipping a fallback password.

Production startup is migration-gated:

    postgres healthy
      -> one-shot migrate service
      -> schema version 2 stamped/verified
      -> API starts with PORTFLOW_SCHEMA_MODE=verify
      -> /readyz becomes healthy
      -> web starts

The API process does not silently create or migrate production schema in verify mode.

Liveness and readiness are separate:

- /healthz proves the API process is alive and reports the application version.
- /readyz verifies runtime initialization, database reachability, and exact schema compatibility.

### PostgreSQL backup / restore

The repository includes operator scripts:

    ./ops/backup-postgres.sh
    PORTFLOW_RESTORE_CONFIRM=YES ./ops/restore-postgres.sh /path/to/portflow.dump

Optional PORTFLOW_ENV_FILE and PORTFLOW_COMPOSE_PROJECT variables let the scripts target a specific deployment.

Restore is intentionally guarded by PORTFLOW_RESTORE_CONFIRM=YES because it is destructive. The restore flow stops API/web, restores PostgreSQL with pg_restore --clean --if-exists, reruns the migration command, then restarts API/web.

## Verification

    cd apps/api
    uv run pytest -q

    cd ../web
    npm run build
    npm audit --omit=dev --audit-level=high

Current local verification target:

- 35 backend/domain/API/storage/recovery/security/scenario tests
- production web build
- zero production npm vulnerabilities

GitHub Actions workflow is committed. The linked GitHub account currently has Actions disabled at account level, so local verification is the canonical proof until that account setting changes.

## API highlights

- GET /api/v1/adapters
- GET /api/v1/adapters/{adapter_id}/preview
- POST /api/v1/adapters/{adapter_id}/ingest
- GET /api/v1/scenarios
- POST /api/v1/scenarios/{scenario_id}/run
- GET /api/v1/auth/me
- GET /healthz
- GET /readyz
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

## v0.3 proof

### Durable offline delivery

- outbound operational events are durably queued while OFFLINE_EDGE
- queue state is persisted separately from the local audit ledger
- reconnect to FULL triggers replay through an explicit delivery adapter
- each successful replay creates a durable ACK receipt
- replay is idempotent: already acknowledged envelopes are not delivered twice
- UI queue count reflects the actual durable spool, not a synthetic timer

Runtime proof:

- 2 events queued during offline incident flow
- 2 events acknowledged on reconnect
- 0 events pending after replay
- max delivery attempts: 1

### Service dependency graph

Each scheduled port call now carries a canonical service chain:

pilot -> tug -> berth -> crane -> cargo -> customs -> departure

The graph has explicit resources and dependency edges. Current synthetic resources include:

- Pilot Alpha / Pilot Bravo
- Tug 14 / Tug 22
- berth resources
- terminal cranes
- Customs Team 1

Incidents change canonical service state:

- pilot delay marks pilot delayed and propagates delay downstream
- tug unavailable marks the assigned tug unavailable and blocks downstream services
- berth conflict blocks the later vessel's berth access and downstream crane/cargo/customs/departure path
- wind restriction blocks pilot/tug movement chains for affected inbound calls

The API exposes an explainable dependency graph for each port call.

### New APIs

- GET /api/v1/replay/pending
- POST /api/v1/replay
- GET /api/v1/replay/receipts
- GET /api/v1/port-calls/{call_id}/dependency-graph

## v0.4 proof

### Recovery proposal engine

PortFlow now evaluates corrective actions without mutating live state.

Current recovery actions:

- reassign a service resource
- move a vessel to a compatible clear berth
- shift an operating window

Each proposal is simulated against a cloned HarborOverview before it is ranked.

Proposal output includes:

- projected total delay minutes
- projected modeled delay exposure
- projected berth conflicts
- projected blocked services
- projected target-call risk
- disruption score
- rationale
- explicit assumptions
- approval-required flag

The engine never auto-applies a proposal.


Each proposal is bound to a recovery-state fingerprint derived from recovery-relevant schedule, active-incident, resource-assignment, and weather-restriction state. If that state changes before approval, the old proposal id becomes stale and apply is rejected.

### Human authority boundary

Recovery execution is a separate explicit action.

Flow:

incident -> generate proposals -> compare projections -> operator approves -> apply -> durable receipt

Applied recovery decisions produce a RecoveryApplicationReceipt with:

- proposal id
- application time
- target port call
- exact actions
- resulting conflicts
- resulting blocked services
- resulting total delay
- resulting modeled cost
- approved_by = human_operator

Receipts are persisted in the SQL operations store and exposed by API.

### Demonstrated recovery cases

Berth overrun:

B07 overrun creates a 55-minute modeled overlap with pc-nova.

Ranked options include:

1. move pc-nova to Berth 15
2. hold pc-nova until B07 clears plus operating buffer

The current synthetic ranking selects Berth 15:

- conflicts: 1 -> 0
- blocked services: incident-blocked chain -> 0
- current modeled arrival window preserved
- B15 crane assignment updates to crane-b15-a

Tug failure:

Tug 14 failure affects every modeled call assigned to that tug, not only the incident's initiating vessel.

The recovery engine generates a compound plan that moves the affected Tug 14 workload to Tug 22 and shifts only the window required to maintain the synthetic 45-minute resource separation.

Runtime proof:

- global blocked services: incident-blocked chain -> 0
- pc-aurora tug state: assigned
- pc-aurora tug resource: tug-22
- downstream departure chain: unblocked

### Recovery APIs

- GET /api/v1/recovery/proposals
- POST /api/v1/recovery/proposals/{proposal_id}/apply
- GET /api/v1/recovery/receipts

## v0.5 proof

### Availability- and capacity-aware resource recovery

Recovery feasibility now considers:

- resource available_from
- resource capacity
- existing service assignments
- synthetic 45-minute pilot/tug separation windows

A third synthetic tug, Tug 31, is available 20 minutes after the initial demo epoch with no pre-existing workload.

For the same Tug 14 failure, the engine currently compares:

Tug 31 plan:

- wait 20 minutes for Tug 31 availability
- move the Tug 14 workload to Tug 31
- projected total delay: 60 minutes
- blocked services after recovery: 0
- disruption score: 75

Tug 22 plan:

- use an already-worked Tug 22 schedule
- shift the Aurora tug window 39 minutes to preserve separation
- projected total delay: 79 minutes
- blocked services after recovery: 0
- disruption score: 94

The lower-disruption Tug 31 plan ranks first. This behavior is regression-tested.

### Recovery-state binding

Proposal ids include a recovery-relevant state fingerprint.

Changing schedule timing, active incidents, resource assignments/status, resource availability/capacity, or movement restrictions changes the fingerprint and invalidates old proposal ids.

Live vessel-map movement and generated timestamps are deliberately excluded so harmless display ticks do not stale an approval.

### Frontend loading

The MapLibre harbor layer is lazy-loaded.

Measured production build:

- initial application JS: about 242 KB minified
- HarborMap/MapLibre path: about 1.01 MB minified, loaded separately
- production npm vulnerabilities: 0

This replaces the previous roughly 1.25 MB synchronous initial JavaScript path.

### Deployable stack

Added:

- FastAPI production Dockerfile
- React multi-stage Node -> Nginx Dockerfile
- Nginx REST + WebSocket reverse proxy
- external /healthz proxy
- docker-compose.prod.yml
- required database secret
- .env.example
- Postgres persistent volume
- API/web health checks

Both images were built from the repository Dockerfiles.

End-to-end stack proof:

Postgres healthy -> API healthy -> Nginx web -> /api/v1/harbor

The stack returned the PortFlow UI, six synthetic vessels, four port calls, service-resource state, and the explicit synthetic-data disclaimer through the web proxy.

On the current Raptor host, Docker build-stage DNS required manual verification with --network=host. That is a host Docker DNS issue, not an application dependency or Dockerfile requirement.

## v0.6 proof

### Identity-bound recovery authority

Recovery proposal visibility remains read-only by default.

Execution now requires an authenticated identity with one of these roles:

- viewer: can inspect authenticated recovery audit receipts but cannot approve
- operator: can approve and apply recovery proposals
- supervisor: can approve and apply recovery proposals

Authorization behavior is enforced by FastAPI dependencies rather than UI-only controls.

Verified HTTP authority matrix:

- anonymous GET /api/v1/auth/me -> 401
- invalid bearer credential -> 401
- viewer GET /api/v1/auth/me -> 200
- anonymous recovery apply -> 401
- viewer recovery apply -> 403
- operator recovery apply -> 200
- anonymous recovery receipt read -> 401
- viewer recovery receipt read -> 200
- supervisor recovery apply -> 200

### Credential handling

PortFlow's current portfolio authentication layer uses opaque bearer credentials.

The server configuration stores only SHA-256 token digests in PORTFLOW_APPROVERS_JSON. Raw operator credentials are not stored in the repository or .env.example.

Digest comparison uses hmac.compare_digest.

The browser keeps the active credential in sessionStorage rather than localStorage so it does not intentionally persist across browser sessions.

This is a bounded portfolio authentication layer, not a claim of enterprise SSO. A production customer deployment should replace or front it with an organization identity provider / OIDC layer.

Generate a digest without putting the raw credential in shell history:

    python -c "import getpass,hashlib; print(hashlib.sha256(getpass.getpass('Operator token: ').encode()).hexdigest())"

Production compose requires both:

- PORTFLOW_DB_PASSWORD
- PORTFLOW_APPROVERS_JSON

Malformed auth configuration fails during API startup.

### Identity-bound receipts

RecoveryApplicationReceipt now records:

- proposal id
- state fingerprint
- target port call
- exact applied actions
- resulting conflicts / blocked services / delay / modeled cost
- operator id
- operator role
- operator display name
- application timestamp

Runtime proof recorded:

operator approval:

- operator id: operator-17
- role: operator
- display name: Mina Torres
- apply: 200

supervisor approval:

- operator id: supervisor-02
- role: supervisor
- display name: Alex Chen
- apply: 200

A viewer can read the resulting audit receipt but cannot create it.

### Operator session UI

The Recovery Plans panel now includes an explicit Operator Session surface.

Unauthenticated state:

- proposals remain visible
- apply controls are disabled
- receipt history is hidden behind authentication
- no automatic approval path exists

Viewer state:

- identity and viewer role are visible
- proposals remain inspectable
- apply remains disabled

Operator / supervisor state:

- verified identity is visible
- explicit Approve & apply action is enabled
- receipt display identifies the approving person and role
- End session clears the session credential

The v0.6 auth/recovery UI was rendered in the real incident state as part of visual QA.

### v0.6 verification

Current verification:

- 32 backend/domain/API/storage/recovery/security tests pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- FastAPI /healthz reports v0.6.0 and authorization_configured=true when approvers are present
- v0.6 API Docker image builds successfully
- v0.6 Nginx web image builds successfully
- docker-compose.prod.yml validates with required authorization configuration

The authorization matrix was runtime-proven against the API process. Full Docker deployment of the auth matrix was not claimed because the execution environment blocked passing test credential configuration into the privileged Docker verification step.

## v0.7 proof

### Canonical deterministic scenario fixtures

Scenario definitions are now owned by the backend instead of existing only as duplicated frontend button logic.

Canonical fixtures:

- berth-crunch: B07 overrun creates a downstream Ocean Nova berth conflict
- tug-loss: Tug 14 failure forces constrained resource recovery planning
- edge-pilot-delay: offline-edge connectivity plus a local pilot-delay event
- wind-hold: deterministic high-wind movement restriction

APIs:

- GET /api/v1/scenarios
- POST /api/v1/scenarios/{scenario_id}/run

Running a fixture resets the synthetic demo and applies the fixture actions in deterministic order.

Regression proof includes:

- repeated berth-crunch runs reproduce the same structural conflict outcome
- edge-pilot-delay enters OFFLINE_EDGE and produces durable queued events
- unknown scenario ids return 404
- tug-loss remains compatible with the constrained recovery engine

The browser Scenario Lab now loads this backend catalog and executes canonical fixture ids. The previous frontend-only scenario definition list is removed.

### Real browser recovery E2E

Playwright is now part of the web development toolchain.

The E2E test uses the installed system Chromium and isolated ports:

- API: 8150
- Vite UI: 5175

The verified browser path is:

1. reset demo through the application API
2. open the real React control tower
3. click the canonical B07 Berth Crunch scenario
4. wait for the Berth 15 recovery proposal
5. verify unauthenticated Apply is disabled
6. enter an E2E operator credential
7. verify operator identity and role through /api/v1/auth/me
8. approve and apply the recovery proposal
9. verify the identity-bound receipt appears in the UI
10. verify berth conflicts are empty
11. verify the credential exists only in sessionStorage for the active browser session
12. reload the page
13. verify operator session and receipt restore correctly

Current browser result:

- 1 Playwright E2E test
- 1 passed
- real Chromium 151 on the Raptor host

Playwright retains trace/screenshot only on failure.

### Configurable development proxy

Vite's backend target is no longer hardcoded for every environment.

PORTFLOW_API_TARGET can redirect the development UI to an isolated API process while preserving:

- REST proxying
- WebSocket proxying
- normal localhost defaults

This allows browser tests and parallel local projects to run without stealing the standard PortFlow API port.

### v0.7 verification

Current gates:

- 35 backend/domain/API/storage/recovery/security/scenario tests pass
- 1 real-browser Playwright recovery-authority E2E passes
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- deterministic scenario catalog is API-backed
- Scenario Lab consumes the canonical backend fixtures
- identity-bound recovery approval remains server-enforced
- browser session restore is tested
- v0.7 API and Nginx/web Docker images build successfully from current source
- API image size: about 113 MB
- web/Nginx image size: about 21 MB

## v0.8 proof

### Explicit external-data provenance

PortFlow now carries data origin as part of the operational model rather than only in documentation.

Each active source records:

- source_id
- domain: ais / weather_tide / berth_plan
- mode: synthetic / recorded / live
- provider
- observed_at
- received_at
- freshness_seconds
- stale_after_seconds
- stale
- health
- record_count
- detail

Vessel, berth, port-call, and weather models carry source_id references back to that provenance record.

HarborOverview exposes the current active sources in data_sources.

A domain may have more than one active source at once. For example, recorded-ais currently updates two modeled vessels while the remaining vessels continue to reference synthetic-ais. PortFlow preserves both source records instead of falsely labeling the entire AIS picture as recorded.

### Dynamic freshness and stale-state handling

Recorded/live freshness is recalculated from observed_at when the harbor overview is produced.

A source automatically becomes stale when its current age exceeds stale_after_seconds.

The harbor metrics include stale_data_sources.

Stale, offline, error, or unconfigured adapter snapshots are not ingestible.

The UI shows source mode, current freshness, stale threshold, health, provider, and source id.

### Recorded fixture adapters

v0.8 ships deterministic recorded-feed adapters for safe offline/demo verification:

- recorded-ais
- recorded-weather
- recorded-berth-plan
- stale-weather-fixture

The stale weather fixture is intentionally older than its freshness threshold and exists to prove stale-data rejection.

These are explicitly labeled recorded fixtures. They are not represented as live providers.

### Adapter APIs

Read-only discovery / preview:

- GET /api/v1/adapters
- GET /api/v1/adapters/{adapter_id}/preview

Operational ingest:

- POST /api/v1/adapters/{adapter_id}/ingest

The ingest authority boundary is server-side:

- anonymous ingest -> 401
- viewer ingest -> 403
- operator / supervisor ingest -> allowed
- stale adapter ingest -> 409

Manual ingest writes a durable operations-ledger event with:

- actor_id
- actor_role
- source_id

### Validate-first, apply-second ingest

Adapter payloads are normalized and validated before any harbor object is mutated.

Current validation includes:

AIS:

- non-empty vessel id
- latitude range
- longitude range
- non-negative speed
- heading range

Weather / tide:

- required numeric weather/tide fields
- non-negative wind, visibility, and wave-height constraints

Berth plan:

- non-empty port-call / berth identifiers
- departure after arrival
- known berth requirement for modeled port calls

Regression coverage proves that a payload containing a valid first record and invalid second record is rejected without partially updating the first vessel.

### Recorded data actually changes the model

Recorded AIS replay changes the modeled vessel positions/speed/heading/ETA and binds affected vessels to source_id=recorded-ais.

Recorded weather replay replaces metocean state and source provenance.

Recorded berth-plan replay applies absolute modeled timing/berth values, binds port calls and referenced berths to recorded provenance, and is idempotent against repeated ingestion.

Source provenance survives snapshot persistence / simulator restart.

Externally sourced vessel positions and metocean values are protected from the background synthetic generator. Once a vessel or weather state is bound to recorded/live provenance, synthetic tick() updates do not silently overwrite it. Synthetic entities continue to evolve normally.

### Live HTTP JSON adapter boundary

PortFlow now implements an environment-configured HTTP JSON live adapter using the same AdapterSnapshot contract.

No live adapter exists by default.

A live adapter appears only when its deployment URL is configured.

Supported optional deployment variables:

- PORTFLOW_AIS_URL / PORTFLOW_AIS_PROVIDER
- PORTFLOW_WEATHER_URL / PORTFLOW_WEATHER_PROVIDER
- PORTFLOW_BERTH_PLAN_URL / PORTFLOW_BERTH_PLAN_PROVIDER

The live endpoint contract is:

    {
      "observed_at": "2026-09-21T02:00:00+00:00",
      "records": [
        { "... domain-specific normalized fields ..." }
      ]
    }

Transport policy:

- deployed URLs must use HTTPS
- plain HTTP is accepted only for localhost / loopback development
- fetch timeout is bounded
- loader/network/shape failures become adapter health=error instead of pretending the feed is healthy
- an old observed_at becomes health=stale
- URLs are deployment configuration, not user-supplied API parameters

The live adapter contract is regression-tested with fresh, stale, failed-loader, and environment-registry cases.

### Truthful mixed-source disclaimer

The harbor disclaimer is derived from actual active source modes.

It distinguishes:

- synthetic-only state
- synthetic + recorded fixture state
- synthetic + live adapter state
- synthetic + recorded + live state

Regression coverage prevents live adapter data from being mislabeled as fully synthetic.

### Data Feeds operations UI

A new Data Feeds panel exposes:

CURRENT HARBOR SOURCES:

- domain
- provider
- source mode
- freshness
- record count
- health
- source id

AVAILABLE ADAPTERS:

- adapter provider/domain
- freshness and stale threshold
- health
- ingest authority state

Unauthenticated and viewer sessions cannot ingest.

Operator/supervisor sessions can ingest healthy adapters.

Stale adapters render as Stale blocked.

The header says NO LIVE FEEDS CONFIGURED unless a real environment-configured live adapter is actually present.

### Real-browser adapter E2E

The Playwright suite now has two Chromium E2Es.

The new adapter path proves:

1. demo reset
2. initial AIS source is synthetic
3. intentionally stale adapter is visibly blocked
4. recorded AIS adapter requires authentication
5. operator authenticates
6. healthy recorded AIS fixture is ingested
7. current AIS source switches to recorded
8. recorded provider is visible in the UI
9. v-aurora source_id becomes recorded-ais in the API state
10. data_sources reports mode=recorded and health=healthy
11. the disclaimer explicitly identifies recorded fixture data

### v0.8 verification

Current gates:

- 51 backend/domain/API/storage/recovery/security/scenario/adapter tests pass
- 2 real Chromium Playwright E2Es pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- recorded adapter ingest survives persistence/restart
- stale sources age dynamically and are blocked from ingest
- malformed payloads are rejected atomically
- partial-domain provenance remains multi-source instead of being flattened
- background synthetic ticks cannot overwrite recorded/live AIS or weather state
- manual ingest carries actor/source audit metadata
- live HTTP adapter boundary is implemented but no live provider is claimed by default
- production compose passes optional live adapter URL/provider configuration into the API container

## v0.9 proof

### Branched port-service dependency DAG

PortFlow no longer presents the port-service model as a single linear chain.

This graph is a deterministic portfolio / decision-support abstraction, not a regulatory or universally mandated port workflow. IMO FAL standards govern facilitation, declarations, electronic exchange, and Maritime Single Window processes; they do not prescribe this exact service ordering. Local ports, terminals, harbour masters, customs authorities, and service providers may execute or release these activities in different sequences or in parallel.

The canonical demo dependency graph is now:

    pilot -> tug -> berth
    berth -> crane -> cargo
    berth -> bunker
    berth -> stores
    berth -> documents
    cargo + documents -> customs
    cargo + customs -> gate
    cargo + bunker + stores + customs + gate -> departure

Each ServiceStep still carries explicit dependency_step_ids. The graph can therefore express parallel post-berth work and multi-parent release conditions instead of pretending every activity is sequential.

New modeled service kinds:

- bunker
- stores
- documents
- gate

New canonical resources include:

- Bunker Barge 4
- Bunker Barge 9
- Bunker Barge 12
- Stores Team 1
- Docs Desk 1
- Gate Team 1

### Standards boundary

The v0.9 service graph intentionally separates two kinds of truth:

- standards-backed coordination facts: port calls involve arrival/stay/departure formalities, electronic authority exchange, berth/nautical planning, and continuously updated operational data;
- demo-model assumptions: the exact dependency edges between cargo, documents, customs, gate, bunker, stores, and departure.

IMO FAL and Maritime Single Window requirements standardize information exchange and formalities. IMO operational port-call guidance is port/trade agnostic and is intended to support local process implementation rather than impose one global terminal workflow.

Port of Rotterdam Port Call Optimisation material shows a concrete local pattern in which terminal cargo end-time and bunker end-time are shared into departure planning. PortFlow uses that as evidence that cargo and bunker completion can legitimately constrain departure planning, while still labeling the exact v0.9 dependency structure as synthetic.

For a production deployment, these dependency edges must be mapped to the target port/terminal operating model and competent-authority rules before the graph is treated as operational policy.

### Shared-resource incident propagation

The new bunker_unavailable incident is resource-bound rather than vessel-only.

If Bunker Barge 4 becomes unavailable, every modeled bunker step assigned to that resource is blocked. Dependency propagation then blocks each affected departure that still requires the bunker service.

The deterministic bunker-loss scenario therefore proves one physical resource failure can affect more than one port call through the service graph.

### Compound shared-workload recovery

Recovery generation now handles both tug and bunker shared-resource failures through the same constrained resource-recovery path.

Candidate feasibility considers:

- resource kind
- current assignments
- capacity
- available_from
- service-specific separation windows
- downstream delay
- blocked services
- current berth conflicts

For the canonical bunker-loss fixture, the engine evaluates the entire workload formerly assigned to Bunker Barge 4 rather than repairing only the selected vessel.

Current synthetic fixture example:

- Bunker Barge 12: 48 modeled total delay minutes, 0 blocked services, disruption score 63
- Bunker Barge 9: 94 modeled total delay minutes, 0 blocked services, disruption score 109

These values are deterministic portfolio-model outputs for the canonical fixture, not a universal port-optimization formula.

The proposal remains decision support only. Operator/supervisor approval is still required before canonical state changes.

### Snapshot service-graph migration

A persisted v0.8 snapshot may contain the former seven service kinds.

On restore, PortFlow validates the canonical service-kind set for every port call. If any call is incomplete, it reconstructs the canonical v0.9 service DAG while retaining the persisted operational entities and state used to build it.

Regression coverage proves a v0.8-style service graph restores with all eleven v0.9 service kinds.

### Dependency-truth UI

The service UI no longer draws a fake linear connector through a branched graph.

The React projection computes topological dependency depth from dependency_step_ids and renders service nodes in dependency columns.

Each non-root node names its actual upstream dependencies, so the visible console remains consistent with the backend DAG.

### Expanded real-browser proof

The Chromium suite now covers three end-to-end paths:

1. incident -> authenticated recovery -> durable receipt -> reload/session restore
2. recorded AIS ingest -> source/provenance UI -> API truth -> page reload persistence, with stale adapter still blocked
3. bunker-loss scenario -> branched DAG UI -> shared blockage across Aurora and Glory -> authenticated compound recovery -> both departures unblocked

### v0.9 verification

Current v0.9 verification gates:

- 56 backend/domain/API/storage/recovery/security/scenario/adapter tests pass
- 3 real Chromium Playwright E2Es pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- Python compile passes
- git diff hygiene passes
- current API and Nginx/web Docker images build from the working source
- isolated PostgreSQL-backed runtime restart preserves the active bunker incident and 11-node service DAG state
- recorded/live AIS and weather ownership remains protected from synthetic tick overwrite
- stale adapter ingest remains rejected
- recovery approval remains identity/role gated
- no live external provider is claimed unless deployment configuration actually supplies one

## v0.10 proof

### Explicit resource calendars

ServiceResource now supports explicit unavailable windows in addition to the existing available_from lower bound.

Each unavailable window carries:

- start_at
- end_at
- reason

Invalid windows whose end is not after start are rejected by the model.

This closes a scheduling gap that available_from cannot represent: a resource may be generally available, become unavailable for maintenance or shift coverage, and then return to service later.

### Calendar-aware feasibility

Recovery feasibility now treats resource calendar outages as hard constraints.

The scheduling loop considers, in order:

- available_from
- explicit unavailable windows
- capacity
- existing assignments
- service-specific separation windows

If a proposed service time falls inside an unavailable window, the candidate is advanced to the end of that window before capacity/separation constraints are evaluated again.

Calendar state is included in the recovery state fingerprint. A proposal therefore becomes stale when a relevant resource calendar changes before approval.

### Decision impact, not metadata only

Regression coverage proves the calendar can change recovery ranking.

In the canonical bunker-loss fixture, Bunker Barge 12 remains the preferred recovery resource under its normal future maintenance calendar:

- 48 modeled total delay minutes
- 0 blocked services
- disruption score 63

A test then moves Bunker Barge 12 into an extended maintenance outage covering the recovery window.

The optimizer responds by ranking Bunker Barge 9 ahead of Bunker Barge 12.

This proves the calendar is part of the decision model rather than display-only metadata.

### Resource Board calendar visibility

The operations console now exposes the first modeled unavailable interval for each resource directly in the Resource Board.

The canonical Bunker Barge 12 fixture shows a future planned-maintenance interval while preserving the existing bunker-loss recovery ranking because that outage begins after the current recovery window.

The real-browser bunker E2E verifies the maintenance constraint is visible alongside the branched service DAG and recovery workflow.

### v0.10 verification

Current gates:

- 59 backend/domain/API/storage/recovery/security/scenario/adapter/calendar tests pass
- 3 real Chromium Playwright E2Es pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- Python compile passes
- canonical bunker recovery remains Bunker Barge 12 at 48 minutes / 0 blocked / disruption score 63 when its future outage does not overlap the recovery window
- an overlapping extended outage flips the preferred recovery candidate to Bunker Barge 9
- calendar changes invalidate recovery state fingerprints
- the Resource Board visibly labels the planned-maintenance interval
- v0.9 provenance, authority, DAG, and PostgreSQL persistence guarantees remain covered by regression tests

## v0.11 proof

### Persistent live-adapter runtime state

Environment-configured live adapters are now reused while their effective configuration is unchanged.

This matters because resilience state is temporal. Recreating an adapter object for every preview would erase:

- the last known healthy payload
- the last successful fetch time
- the consecutive error streak

If URL/provider configuration changes, the adapter instance is intentionally replaced and begins with clean runtime state.

### Last-known-good preview

A healthy live fetch records a deep copy of the last-known-good AdapterSnapshot.

If a later fetch fails:

- fresh last-known-good data -> health=degraded
- expired last-known-good data -> health=stale
- no last-known-good data -> health=error

Cached previews carry:

- last_success_at
- consecutive_errors
- using_cached_records=true
- the original observation timestamp
- freshness recalculated against the current request time

The failure detail identifies the exception type but does not expose arbitrary exception text.

### Cached data cannot mutate operational truth

PortFlow now allows operational ingest only when adapter health is exactly healthy.

This closes an earlier gap where degraded health was not explicitly rejected.

A degraded cached preview may help an operator understand the last known upstream state, but it cannot become a new canonical harbor observation.

This preserves the boundary:

preview/cache != ingest != canonical operational truth

### Thread-safe adapter state

Each live HttpJsonAdapter serializes snapshot state updates with a lock.

The configured live-adapter registry also uses a lock while reconciling environment configuration with existing instances.

This avoids concurrent preview/ingest requests racing last-good state or error counters.

### Data Feeds resilience UI

The Data Feeds panel now labels all adapter types under AVAILABLE ADAPTERS instead of incorrectly calling the whole list recorded fixtures.

When resilience state exists, the UI exposes:

- LAST-KNOWN-GOOD CACHE
- consecutive error count
- degraded / stale / error health
- Cached preview action state
- Feed unavailable state
- mode-aware Ingest live versus Ingest fixture labels

Cached or unhealthy adapters remain disabled for ingest.

### v0.11 verification

Current gates:

- 65 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience tests pass
- API integration coverage proves live adapter runtime state survives across repeated preview requests
- fresh cache falls back to degraded
- expired cache becomes stale
- no-cache failure becomes error with an increasing error streak
- degraded cached snapshots are rejected by the simulator ingest boundary
- configured live adapter identity is reused only while configuration is unchanged
- 3 real Chromium Playwright E2Es pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- Python compile passes
- v0.10 calendar, v0.9 DAG/recovery, and v0.8 provenance ownership guarantees remain covered by regression tests

## v0.12 proof

### Provenance-bound decision confidence

Recovery proposals now carry an explicit DecisionConfidence state:

- demo
- low
- medium
- high

This is not a probability score.

It is a deterministic statement about the provenance and health of the active operational inputs that support the current harbor picture.

Rules:

- all active inputs synthetic -> demo
- missing, stale, offline, unconfigured, or error input -> low
- degraded/cached input -> medium
- mixed synthetic/external or recorded-replay input -> medium
- all active inputs healthy live observations -> high

The model intentionally refuses to call recorded replay or mixed synthetic/external state high-confidence.

### Data-quality warnings on every recovery plan

RecoveryProposal now includes:

- decision_confidence
- data_quality_warnings

The Recovery Plans UI surfaces both directly beside the operational projection.

Examples include:

- all active operational inputs are synthetic demo sources
- recorded replay data is active and is not a live provider observation
- operational picture mixes synthetic and external provenance
- a named active source is stale
- a source is using degraded or cached upstream state

The purpose is not to hide a recommendation when data quality is weaker. It is to expose why the operator should trust it less.

### Fresh source data invalidates old recovery proposals

Recovery state fingerprints now include active data-source provenance:

- source id
- domain
- mode
- observed_at
- stale threshold/state
- health
- cached-record state
- consecutive error count

A new AIS/weather/berth observation can therefore change the recovery fingerprint even when the physical incident itself has not changed.

This closes a stale-decision gap where a proposal could previously remain apparently valid after the operational evidence supporting it had changed.

### Confidence remains advisory, not authority

Decision confidence does not bypass the existing approval model.

A HIGH proposal still requires operator/supervisor approval.

A DEMO/MEDIUM/LOW proposal remains visible for inspection, with its warnings, but the product does not convert the confidence label into autonomous execution.

Authority remains:

current operational state + provenance
  -> deterministic proposal + confidence
  -> human approval
  -> canonical mutation + receipt

### v0.12 verification

Current gates:

- 69 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence tests pass
- synthetic-only recovery proposals are explicitly DEMO
- recorded AIS ingestion changes recovery confidence to MEDIUM and changes the recovery fingerprint
- stale active provenance drives LOW confidence
- an all-healthy-live active-source fixture can reach HIGH confidence
- recovery fingerprints are bound to active source provenance
- 3 real Chromium Playwright E2Es pass
- the bunker recovery E2E explicitly verifies DATA CONFIDENCE · DEMO
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- Python compile passes
- v0.11 adapter resilience, v0.10 calendar, v0.9 DAG/recovery, and v0.8 provenance-ownership guarantees remain covered by regression tests

## v0.13 proof

### Modeled service occupancy durations

ServiceStep now carries duration_minutes in addition to planned_at.

Canonical demo durations include:

- pilot: 30 minutes
- tug: 45 minutes
- berth-access step: 15 minutes
- crane allocation/setup: 30 minutes
- cargo operation: 180 minutes
- bunker service: 60 minutes
- stores: 30 minutes
- documents: 30 minutes
- customs: 30 minutes
- gate: 30 minutes
- departure clearance: 20 minutes

These are deterministic portfolio-model assumptions for the demo fixture, not universal legal or operational standards.

Legacy snapshots whose service steps do not contain a duration are migrated to the current canonical duration table on restore.

### Interval-based resource capacity

Resource feasibility no longer treats a service as a single point in time.

Each assignment occupies a half-open interval:

    [planned_at, planned_at + duration)

For an alternative resource, PortFlow builds intervals where its existing assignments already consume the full configured capacity.

A new assignment may overlap existing work while capacity remains available.

It may not overlap a saturation interval.

This gives capacity an operational meaning:

- capacity 1 -> one concurrent modeled assignment
- capacity 2 -> two concurrent modeled assignments
- and so on

Regression tests prove:

- capacity 1 delays an overlapping bunker job
- capacity 2 allows one overlapping assignment
- capacity 2 delays a third assignment when two existing jobs overlap

### Full-interval calendar enforcement

Resource unavailable windows now constrain the entire modeled service interval, not only its start time.

A 60-minute bunker service starting before a maintenance outage is still infeasible if the service would extend into the outage.

The scheduler advances the assignment until its full interval no longer overlaps the blocked calendar period.

### Recovery fingerprint includes service schedule occupancy

Recovery state fingerprints now bind:

- service id
- assigned resource id
- planned service start
- modeled duration
- service state

A service duration, resource assignment, or schedule-state change can therefore invalidate an old recovery proposal.

### Duration visibility in the service DAG

The operations UI exposes modeled duration on every service node beside its resource.

The bunker-loss Chromium path explicitly verifies the 60-minute bunker duration while still proving:

- branched DAG truth
- shared-resource blockage
- operator approval
- shared-resource recovery
- departure unblocking

### v0.13 verification

Current gates:

- 74 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity tests pass
- capacity-1 overlap delays correctly
- capacity-2 permits one overlap
- capacity-2 saturation delays a third assignment
- maintenance overlap is checked across the entire service interval
- legacy zero-duration service steps migrate on restore
- canonical bunker recovery remains Bunker Barge 12 at 48 minutes / 0 blocked / disruption score 63
- 3 real Chromium Playwright E2Es pass
- production TypeScript/Vite build passes
- production npm audit reports 0 vulnerabilities
- Python compile passes
- v0.12 confidence, v0.11 adapter resilience, v0.10 calendar, v0.9 DAG/recovery, and v0.8 provenance guarantees remain covered by regression tests

## v0.14 proof

### Compound cross-resource recovery

PortFlow now coordinates recovery across multiple active recoverable resource failures that affect the same primary port call.

The planner:

- groups active recoverable resource failures by target port call
- orders failures by service dependency depth
- enumerates alternative resource combinations with a Cartesian product
- bounds the search to the first 12 combinations
- applies each failure sequentially to one evolving cloned simulator state
- emits a compound proposal only when at least two service kinds are covered

Sequential simulation matters: a later resource decision sees the assignments, schedule shifts, capacity usage, and downstream consequences created by earlier decisions in the same proposal.

RecoveryProposal and RecoveryApplicationReceipt both retain the backward-compatible primary incident_id and add incident_ids for the full linked incident set.

Applying a recovery proposal does not resolve the underlying incidents. Incidents describe real-world failure state; recovery describes an operational adaptation around that state. Incident lifecycle remains explicit and separate.

### Canonical dual-resource fixture

The deterministic scenario dual-resource-loss injects:

- Tug 14 unavailable for Aurora, modeled impact 40 minutes
- Bunker Barge 4 unavailable for Aurora, modeled impact 45 minutes

The canonical best compound proposal is:

- Compound recovery: Tug 22 + Bunker Barge 9
- 2 linked incident IDs
- tug + bunker service actions
- 5 recovery actions
- 124 minutes projected total delay
- 0 projected blocked services
- disruption score 149

Single-resource recovery proposals under the same dual failure leave downstream work blocked. The compound plan clears the modeled downstream blockage, so this is an operational planning behavior rather than a UI-only label.

### Compound authority and audit

Compound recovery preserves the existing control boundary:

current operational state + provenance
  -> deterministic compound proposal
  -> explicit operator/supervisor approval
  -> operational mutation
  -> durable receipt linked to all incident IDs

No proposal auto-applies.

The Recovery Plans UI marks multi-incident proposals as COMPOUND · N INCIDENTS.

### v0.14 release gate

The release is accepted only when all of the following pass:

- 77 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound tests
- Python compile
- production TypeScript/Vite build
- production npm audit with 0 relevant vulnerabilities
- 4 real Chromium Playwright E2Es
- Docker API and WEB image builds
- isolated Docker runtime health reports version 0.14.0
- the runtime dual-resource-loss scenario reproduces the compound proof above with 0 blocked services
- release diff contains intended files only
- remote main is advanced non-force
- lightweight tag v0.14.0 points to the same commit as main
- remote changed blobs match the exact locally verified content

## Next engineering milestone

v0.15 should prioritize product realism and deployment rather than expanding PortFlow into the separate vessel-intelligence runtime:

- configurable / empirical service-duration calibration while preserving synthetic vs recorded/live provenance
- retry, backoff, and contingency scheduling
- hosted production deployment with HTTPS, persistent PostgreSQL, migrations, observability, backups, and resilient startup
- stronger scenario snapshots, replayability, and evidence controls
- a documented future event/API boundary for vessel-side operational events without prematurely coupling the codebases

## v0.15 proof

### Provenance-bound service-duration calibration

Service-duration assumptions are now canonical modeled state rather than anonymous constants.

Each service kind has a ServiceDurationCalibration containing:

- service kind
- duration in minutes
- source id
- source mode: synthetic, recorded, or live
- provider
- observation time
- optional source detail

The default portfolio fixture remains explicitly synthetic. This preserves the existing demo behavior while making the calibration assumption inspectable.

### Calibration authority boundary

The calibration catalog is readable without approval authority.

Changing calibration requires the same operator/supervisor role used for other operational mutations.

A calibration update:

- validates source identity, mode, observation time, and health against provenance
- rejects stale or unhealthy evidence
- updates every modeled service step of that kind
- persists the changed calibration in HarborOverview snapshots
- emits an identity-bound service_calibration event
- changes the recovery state fingerprint
- participates in recovery decision confidence

This means PortFlow cannot claim HIGH decision confidence while schedule occupancy still depends on missing, stale, synthetic, or recorded calibration evidence.

### Backward-compatible snapshot migration

Snapshots created before v0.15 do not contain service_duration_calibrations.

On restore, PortFlow creates the canonical synthetic calibration set and adds its provenance source. Legacy zero-duration service steps continue to migrate to the current calibrated duration.

### API surface

- GET /api/v1/service-duration-calibrations exposes the active calibration set
- POST /api/v1/service-duration-calibrations requires operator/supervisor authority
- stale calibration evidence returns 409 without mutating canonical state

The Data Sources UI recognizes service_calibration as a first-class provenance domain.

### v0.15 calibration increment verification

Current gate for this increment:

- 81 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration tests
- Python compile
- production TypeScript/Vite build
- npm audit
- existing Chromium recovery E2Es
- version metadata aligned at 0.15.0

The next v0.15 increment after calibration is the retry/backoff state machine documented below.


## v0.15 retry/backoff proof

### Bounded live-adapter retry state

Live HTTP adapters no longer attempt an upstream request on every preview refresh after a failure.

After a transport or payload failure, PortFlow records:

- last_attempt_at
- consecutive_errors
- retry_delay_seconds
- next_retry_at
- last_success_at
- whether last-known-good records are being shown

The first retry delay is based on a 5-second default. Repeated failures use exponential growth capped at 300 seconds.

A deterministic ±20% jitter is derived from adapter id + error count. This spreads retries without introducing non-reproducible test behavior.

### Retry suppression

If a preview request arrives before next_retry_at:

- the upstream loader is not called
- consecutive_errors does not increase
- last_attempt_at does not change
- the existing cached/error state is returned
- the response explicitly says retry backoff is active

Once next_retry_at is reached, the next preview is allowed to contact the upstream provider.

A successful live response clears:

- consecutive_errors -> 0
- next_retry_at -> null
- retry_delay_seconds -> 0

Healthy last-known-good cache semantics remain unchanged.

### UI and API observability

Adapter preview provenance exposes the retry state directly.

The Data Sources UI shows:

- RETRY BACKOFF
- the current retry-delay window
- the next scheduled retry time
- Retry scheduled on the disabled ingest action

The existing stale/degraded/non-ingestible boundary remains intact.

### v0.15 retry increment verification

Current gate after calibration + retry/backoff:

- 84 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff tests
- Python compile
- production TypeScript/Vite build
- npm audit with 0 vulnerabilities
- 4 real Chromium E2Es, including visible retry-backoff state for a deliberately unavailable live adapter
- fresh API and WEB Docker builds pass
- isolated runtime proof confirms immediate retry suppression and larger due-time backoff

The next v0.15 increment after retry/backoff is contingency scheduling, documented below.


## v0.15 contingency recovery proof

### Stale recovery plans return replacements instead of a dead-end

PortFlow now retains a bounded in-memory history of recently generated recovery proposals.

If an operator tries to approve a proposal that is no longer valid under current harbor state, the backend does not auto-apply a substitute and does not return only a generic stale error.

It returns a structured 409 contingency contract containing:

- the stale proposal id
- target port call
- stale and current state fingerprints
- selected recovery resources that are now unavailable
- ranked replacement proposals relevant to the same incidents/service kinds
- auto_apply=false
- an explicit reason requiring a new operator approval

Proposal history is intentionally ephemeral in this increment. Durable decision-evidence snapshots remain a later deployment/evidence milestone.

### Recovery-resource failure before approval

Existing tug_unavailable and bunker_unavailable incidents now accept an optional explicit target_resource_id.

This supports the real contingency case where a backup resource fails after a recovery plan was generated but before approval.

Rules:

- the explicit resource must exist and match the incident service kind
- failing an already assigned resource preserves the existing delay/propagation behavior
- failing an unassigned backup marks availability truth without inventing a port-call delay
- current proposal generation excludes UNAVAILABLE alternatives

Canonical proof:

    Bunker Barge 4 unavailable
      -> preferred recovery selects Bunker Barge 12
      -> Bunker Barge 12 becomes unavailable before approval
      -> old plan returns structured 409
      -> Bunker Barge 9 appears as ranked replacement
      -> no automatic mutation occurs
      -> operator explicitly approves Bunker Barge 9
      -> bunker/departure blockage clears

The original Bunker Barge 4 and Bunker Barge 12 incidents remain active; recovery adapts around failures rather than falsely resolving them.

### Browser behavior

The Recovery Plans UI recognizes the structured stale-plan response.

It replaces the stale cards with ranked current alternatives and displays a visible CONTINGENCY notice naming unavailable selected resources and stating that a new explicit approval is required.

The replacement still uses the normal identity-bound approval path.

### v0.15 contingency increment verification

Current gate after calibration + retry/backoff + contingency:

- 86 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff/contingency tests
- Python compile
- production TypeScript/Vite build
- npm audit
- 5 real Chromium E2Es, including a real stale Bunker Barge 12 plan -> Bunker Barge 9 contingency -> re-approval flow
- fresh API and WEB Docker builds pass
- isolated runtime proof confirms stale Barge 12 selection -> structured 409 -> Barge 9 replacement -> explicit re-approval -> 0 blocked services

The next v0.15 increment is deployment hardening: migrations/startup checks, production PostgreSQL profile, readiness, observability, backup/restore, and hosted proof.


## v0.15 deployment hardening proof

### Versioned schema boundary

PortFlow persistence has an explicit schema_version table. The current evidence build uses CURRENT_SCHEMA_VERSION=2.

OperationsStore exposes:

- migrate_schema()
- verify_schema()
- schema_status()
- database_ping()

The original v0 -> v1 migration was intentionally conservative. The evidence increment adds an explicit additive v1 -> v2 migration for immutable recovery-proposal and scenario-run evidence tables. Unknown/newer versions still fail closed rather than being silently rewritten.

init_schema() remains only as a backward-compatible test/dev helper.

### Explicit migration command

Production migration is a separate command:

    python -m portflow_api.migrate

The production Compose stack runs this command in a one-shot migrate service before the API starts.

The API then starts with:

    PORTFLOW_SCHEMA_MODE=verify

If PostgreSQL is unreachable, required tables are missing, or schema version differs from the application expectation, production API startup fails instead of mutating the database.

### Liveness vs readiness

/healthz is process liveness only.

/readyz reports and validates:

- runtime_ready
- schema_mode
- database reachability
- expected schema version
- current schema version
- missing tables
- compatibility
- whether operator authorization is configured

The production API healthcheck now targets /readyz.

Nginx proxies both /healthz and /readyz through the single web origin.

### Single API image for migration and runtime

The API Docker image no longer performs a second source-dependent uv sync after copying application code.

Runtime dependencies are installed from the lockfile before source copy and the application runs from PYTHONPATH=/app/src.

This removes an unnecessary build-system fetch from the source layer and makes source-only rebuilds less network-sensitive.

The same tagged API image is reused by both the migrate and api services.

### PostgreSQL migration/readiness runtime proof

An isolated production Compose project was booted from a clean PostgreSQL volume.

Observed chain:

- Postgres health: healthy
- migrate container: exited 0
- API mode: verify
- /readyz: ok=true
- database_reachable=true
- expected_version=2
- current_version=2
- missing_tables=[]
- compatible=true
- web origin exposed readiness successfully

### Backup/restore runtime proof

The hardened production stack was given a persisted bunker-loss scenario.

Measured round-trip:

- active incidents before backup: 1
- PostgreSQL custom-format dump size: 17,941 bytes
- active incidents after destructive demo reset: 0
- restore script executed pg_restore, migration verification, and API/web restart
- active incidents after restore: 1
- persisted incident rows after restore: 1
- schema remained at the then-current compatible version; the evidence increment later advances this contract to version 2

This proves both canonical harbor snapshot state and durable incident storage survive a dump/reset/restore cycle.

### v0.15 deployment gate

Current gate after calibration + retry/backoff + contingency + deployment hardening:

- 89 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff/contingency/schema/readiness tests
- Python compile passes
- production TypeScript/Vite build passes
- npm audit reports 0 vulnerabilities
- 5 real Chromium E2Es pass
- production Compose config renders with migration dependency + verify mode + /readyz
- hardened API and WEB Docker images build from current source
- clean PostgreSQL migration/readiness boot passes
- PostgreSQL backup/reset/restore round-trip passes
- GitHub CI now validates production Compose, operator-script syntax, and both Docker images

The next v0.15 deployment work after this checkpoint is durable proposal/evidence snapshots and public portfolio deployment.


## v0.15 TLS and observability proof

### Optional HTTPS overlay

PortFlow now includes docker-compose.tls.yml as an opt-in production overlay.

The base production stack remains usable on HTTP for local/private environments. Adding the TLS overlay provides:

- HTTP -> HTTPS 308 redirect
- TLS 1.2 and TLS 1.3 only
- mounted deployment certificate/private key
- HSTS
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: no-referrer
- Permissions-Policy disabling camera, microphone, and geolocation
- Cross-Origin-Opener-Policy: same-origin
- REST, WebSocket, health, and readiness proxying over the HTTPS origin

The plain HTTP Nginx profile also emits the non-HSTS security headers.

TLS deployment variables are documented in .env.example:

- PORTFLOW_HTTPS_PORT
- PORTFLOW_PUBLIC_HTTPS_ORIGIN
- PORTFLOW_TLS_CERT_FILE
- PORTFLOW_TLS_KEY_FILE

### Metrics boundary

The API exposes an internal Prometheus-text /metrics endpoint.

Current gauges:

- portflow_runtime_ready
- portflow_schema_compatible
- portflow_authorization_configured
- portflow_active_incidents
- portflow_blocked_services
- portflow_stale_data_sources

Current counters:

- portflow_calibration_updates_total
- portflow_adapter_ingests_total
- portflow_recovery_approvals_total
- portflow_recovery_contingencies_total
- portflow_replay_acks_total
- portflow_scenario_runs_total
- portflow_http_requests_total with method, route template, and status labels

HTTP metrics use FastAPI route templates rather than concrete entity ids, avoiding an unbounded path-label cardinality pattern.

Operational metrics are intentionally not exposed through the public Nginx origin. Public /metrics returns 404. A monitoring collector should scrape the API from the trusted internal network.

### Structured request logging

Every HTTP request emits a JSON event through the Uvicorn logging pipeline.

The record contains:

- UTC timestamp
- event=http_request
- HTTP method
- route template
- response status
- duration_ms

Bodies, bearer credentials, query strings, and entity ids embedded in concrete paths are not copied into the structured request record.

### TLS and observability runtime proof

An isolated PostgreSQL-backed production stack was booted with a one-day self-signed proof certificate.

Verified runtime behavior:

- HTTPS /readyz -> 200
- negotiated HTTP/2 through Nginx
- schema verify mode remained healthy
- Strict-Transport-Security present
- nosniff, DENY frame policy, no-referrer, Permissions-Policy, and COOP headers present
- HTTP request to /proof?x=1 -> 308 with query-preserving HTTPS Location
- public HTTPS /metrics -> 404
- bunker-loss scenario executed through HTTPS
- internal metrics reported runtime_ready=1
- internal metrics reported schema_compatible=1
- internal metrics reported active_incidents=1
- internal metrics reported blocked_services=4
- scenario_runs_total incremented to 1
- HTTP counter used /api/v1/scenarios/{scenario_id}/run as the label
- container log emitted a JSON request record for the scenario POST with status 200 and duration_ms
- Nginx runtime config confirmed ssl_protocols TLSv1.2 TLSv1.3

### v0.15 TLS/observability gate

Current gate:

- 91 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff/contingency/schema/readiness/observability tests
- Python compile passes
- production TypeScript/Vite build passes
- npm audit reports 0 vulnerabilities
- 5 real Chromium E2Es pass
- base production Compose renders
- TLS overlay Compose renders
- API and web Docker images build from current source
- isolated HTTPS + secure-header runtime proof passes
- internal Prometheus metrics runtime proof passes
- structured JSON request logging runtime proof passes
- GitHub CI validates both base and TLS Compose configurations

The remaining v0.15 work is durable proposal/evidence snapshots, then a public portfolio deployment while preserving synthetic-data labeling.


## v0.15 durable decision evidence proof

### Immutable recovery-proposal evidence batches

Recovery planning is no longer represented only by the simulator's bounded in-memory proposal history.

Every generated recovery batch now produces a durable RecoveryProposalEvidenceBatch containing:

- evidence_id
- generated_at
- requested_call_id
- trigger
- optional stale_parent_proposal_id
- the exact ranked RecoveryProposal list shown for that state

The evidence id is content-derived from:

- trigger
- requested call
- stale parent proposal id
- recovery-state fingerprint material
- ordered proposal ids

Repeated polling of the same recovery state therefore deduplicates instead of creating unbounded duplicate evidence rows.

Changed operational state creates a new evidence id even when there are zero viable proposals.

Current evidence triggers include:

- planning
- scenario
- contingency
- explicitly named internal/test planning triggers

The bounded in-memory proposal cache still exists for fast runtime access, but it is repopulated from recent durable evidence when the API starts.

This means stale-plan context can survive an API process restart.

### Durable scenario-run evidence

Every canonical scenario run now stores a ScenarioRunEvidence record with:

- unique run_id
- ran_at
- the exact stored ScenarioFixture definition and actions
- the HarborOverview snapshot after applying the scenario
- the ranked recovery proposals generated from that snapshot

Demo reset deliberately does not delete decision evidence.

Operational state can therefore be reset while the historical decision record remains available for audit.

### Authenticated evidence APIs

Evidence is an authenticated audit surface.

Viewer, operator, and supervisor identities can read evidence. Anonymous access is rejected.

APIs:

- GET /api/v1/evidence/recovery-proposals
- GET /api/v1/evidence/scenario-runs
- GET /api/v1/evidence/scenario-runs/{run_id}/pack

Scenario evidence can be filtered by scenario_id.

### Content-addressed evidence packs

The per-run pack endpoint returns:

- pack_version = portflow-evidence-v1
- canonical SHA-256 of the stored scenario-run payload
- full ScenarioRunEvidence
- replay_input containing the stored scenario id and exact stored actions

The checksum is stable across repeated reads of the same immutable run.

The pack is designed to be portable and tamper-detectable. It contains enough input/output context to reproduce or independently inspect the modeled scenario path without pretending that a later wall-clock replay must produce byte-identical timestamps or ids.

### Schema v2

Evidence persistence advances the production schema contract from version 1 to version 2.

v2 adds:

- recovery_proposal_evidence
- scenario_run_evidence

The migration is additive.

Runtime migration proof used the previous v1 production API image to create a real Postgres v1 database, then used the current image to migrate that same database to v2.

Observed:

- schema before migration: 1
- evidence tables absent before migration
- schema after migration: 2
- recovery_proposal_evidence present
- scenario_run_evidence present
- /readyz in verify mode reported version 2 compatible

### Restart-proof contingency evidence

Runtime proof:

1. create v1 Postgres with the previous production image
2. migrate the same database to v2
3. start the current API in verify mode
4. run the canonical bunker-loss scenario
5. persist its scenario evidence and proposal evidence
6. capture the Bunker Barge 12 recovery proposal id
7. make Bunker Barge 12 unavailable before approval
8. restart the API process without changing the database
9. retrieve the same scenario evidence pack after restart
10. apply the old Barge 12 proposal id
11. receive structured HTTP 409 stale contingency
12. recover Bunker Barge 9 as the ranked replacement

Measured proof:

- evidence pack survived restart
- pack SHA-256 length: 64 hex characters
- stale apply after restart: HTTP 409
- unavailable resource: bunker-barge-12
- replacement includes bunker-barge-9
- durable recovery-proposal evidence rows: 3
- durable scenario-run evidence rows: 1

This closes the earlier gap where a process restart could erase the context required to explain a stale recovery proposal.

### v0.15 evidence gate

Current local gate:

- 94 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff/contingency/schema/readiness/observability/evidence tests
- Python compile passes
- production TypeScript/Vite build passes
- npm audit reports 0 vulnerabilities
- 5 real Chromium E2Es pass
- real Postgres v1 -> v2 migration passes
- API verify-mode schema v2 readiness passes
- scenario evidence survives API restart
- stale recovery context survives API restart
- content-addressed evidence pack survives API restart

The remaining productization work is public portfolio deployment and the documented event/API boundary for a future vessel-side intelligence runtime.


## v0.15 public portfolio deployment proof

### Live portfolio URL

PortFlow is publicly reachable at:

    https://b2gdjx1c.basicdeploy.com

The public deployment is intentionally a shared synthetic portfolio sandbox. It is not a live port feed, not a customer tenancy, and not an operational production control plane.

### Single-origin BasicDeploy runtime

BasicDeploy proxies the public HTTPS hostname to port 8080 inside the container.

The public deployment therefore runs:

    BasicDeploy HTTPS proxy
      -> FastAPI on 0.0.0.0:8080
      -> REST / WebSocket / readiness
      -> optional built React frontend from PORTFLOW_STATIC_DIR
      -> PostgreSQL schema portflow_portfolio

The frontend and API share one origin, so no separate public API hostname or CORS deployment layer is required for the portfolio build.

### Public safety boundary

The public boot profile sets:

    PORTFLOW_SCHEMA_MODE=verify
    PORTFLOW_STATIC_DIR=/workspace/portflow/apps/web/dist
    PORTFLOW_PUBLIC_MODE=1
    PORTFLOW_APPROVERS_JSON=[]

Consequences:

- schema migration runs before verify-mode startup
- recovery approval remains unavailable to anonymous public visitors
- evidence APIs remain authentication-protected
- public /metrics returns 404
- scenario/reset endpoints operate only on the shared synthetic demo state

Internal metrics remain available in non-public deployment profiles.

### Synthetic labeling proof

Outside-in public API verification returned the explicit disclaimer:

    Demonstration only. No live external feeds are active. Vessel, port-call, weather, risk, incident, service, and operational data are synthetic.

The active public sources were:

- synthetic-ais / synthetic
- synthetic-weather / synthetic
- synthetic-berth-plan / synthetic
- synthetic-service-calibration / synthetic

Running the public bunker-loss fixture produced:

- scenario = bunker-loss
- active incidents = 1
- blocked services = 4
- recovery decision confidence = DEMO only

The public portfolio therefore does not present synthetic state as live maritime operations.

### PostgreSQL compatibility fix discovered by live deploy

The first BasicDeploy boot exposed a real portability bug.

BasicDeploy provides a standard postgres:// or postgresql:// DATABASE_URL, while PortFlow uses psycopg v3.

Without normalization, SQLAlchemy selected the legacy psycopg2 dialect and boot failed with:

    ModuleNotFoundError: No module named 'psycopg2'

The fix is applied in two layers:

- OperationsStore centrally normalizes postgres:// and postgresql:// to postgresql+psycopg://
- the BasicDeploy boot URL, after applying its schema search_path, is also normalized to postgresql+psycopg://

A regression test now locks the central normalization behavior.

### Free-plan cold-start / wake resilience

BasicDeploy Free containers auto-sleep.

BasicDeploy invokes /workspace/.bd_boot.sh on wake, so the deployment registers the PortFlow boot script there.

Live sleep/wake testing exposed two additional deployment bugs and closed both:

1. BasicDeploy executes the wake hook through POSIX sh, so Bash-only set -o pipefail failed.
2. Concurrent wake triggers could launch two Uvicorn processes and race for port 8080.

The final hook is POSIX sh-compatible and uses a PID-backed atomic boot lock.

Clean sleep/wake proof:

- first request displayed BasicDeploy's temporary Waking up page
- wake hook migrated/verified schema v3
- exactly one Uvicorn process remained
- lock PID matched the Uvicorn PID
- /healthz returned 200
- /readyz returned schema v3 compatible
- no duplicate bind error occurred

The Free deployment can therefore cold-start after idle sleep without a manual app restart. It still has a cold-start delay by design.

### Source-only public deploy bundle

deploy/basicdeploy_bundle.sh packages only:

- deploy/basicdeploy_boot.sh
- deploy/basicdeploy_prepare.sh
- API src/
- API pyproject.toml
- API uv.lock
- built web dist/

The helper rejects accidental .venv or __pycache__ content.

Current proof bundle size is approximately 468 KB rather than the 23 MB runtime-contaminated archive produced when a live virtual environment was accidentally included during an intermediate re-pack.

### Public deployment gate

Current gate:

- 101 backend/domain/API/storage/recovery/security/scenario/adapter/calendar/resilience/confidence/capacity/compound/calibration/backoff/contingency/schema/readiness/observability/evidence/public-mode/integration tests
- source-only deploy bundle generation passes
- deploy scripts pass POSIX sh syntax validation
- public HTTPS /healthz passes
- public HTTPS /readyz reports schema v3 compatible
- public /metrics returns 404
- public harbor state preserves explicit synthetic disclaimer
- public recovery confidence remains DEMO for synthetic-only scenario state
- Free-plan sleep/wake cold-start passes with one Uvicorn process
- live BasicDeploy PostgreSQL boot passes with psycopg v3 URL normalization

The v0.15 public deployment now includes the completed vessel-runtime contract discovery surface while keeping integration credentials unconfigured on the public sandbox.


## v0.15 vessel-runtime boundary proof

PortFlow's final v0.15 architecture increment is a versioned integration boundary for a future separate vessel-side intelligence runtime.

### Separate authority planes

Human approvals use PORTFLOW_APPROVERS_JSON.

Vessel-runtime integrations use PORTFLOW_INTEGRATIONS_JSON with independent token hashes and vessel allowlists.

An integration token cannot approve recovery.

Container proof returned HTTP 401 when a valid vessel integration token was presented to the recovery-apply endpoint.

### Versioned contracts

Inbound event: portflow.vessel-event.v1

Receipt: portflow.vessel-event-receipt.v1

Coordination snapshot: portflow.coordination.v1

Contract discovery:

    GET /api/v1/integration/contracts

### Schema v3

The vessel boundary advances the additive schema contract from v2 to v3.

v3 adds vessel_runtime_event.

Real PostgreSQL proof used the previous v2 evidence image and the current image against the same database:

- v2 migration -> current_version=2
- vessel_runtime_event absent
- current migration -> current_version=3
- vessel_runtime_event present
- verify-mode readiness -> expected_version=3, current_version=3, compatible=true

### Idempotent durable event proof

A normalized Aurora readiness event was submitted with an authenticated integration token.

Observed:

- first delivery -> duplicate=false
- exact retry -> duplicate=true with the same accepted_at
- same event id with changed content -> HTTP 409
- event remained queryable after API process restart

### Advisory-only coordination proof

The authenticated Aurora integration requested the pc-aurora coordination snapshot.

Observed:

- contract_version=portflow.coordination.v1
- vessel_id=v-aurora
- advisory_only=true
- requires_human_approval=true
- actuation_allowed=false
- port-call stages and service dependencies included

This boundary does not give PortFlow direct vessel actuation authority.

### Repository boundary

Raw ship sensors, local perception, machinery intelligence, navigation reasoning, actuator integration, and vessel-local safety interlocks remain outside PortFlow.

They belong in the future vessel-runtime repository.

PortFlow consumes only normalized operational events and returns port-side coordination/advisory state.

See docs/VESSEL_RUNTIME_BOUNDARY.md for the full contract.

### v0.15 vessel-boundary gate

Current gate includes:

- 101 backend tests across existing product behavior plus integration boundary coverage
- Python compile
- real PostgreSQL v2 -> v3 migration
- authenticated event first/duplicate/conflict proof
- integration-vessel allowlist enforcement
- integration-token recovery denial
- advisory-only coordination proof
- integration ledger persistence across API restart

With this boundary documented and executable, the v0.15 PortFlow productization roadmap is complete.

## v0.16 crew operational exception view

PortFlow v0.16 consumes the privacy-minimized crew exception lifecycle shipped
by Maritime Runtime v0.0.78 without expanding PortFlow into a crew-private
system of record.

### Human view, machine ingest

The machine integration plane remains:

    POST /api/v1/integration/vessel-events

with vessel-scoped integration credentials.

Human port/shore users now have a separate read-only surface:

    GET /api/v1/operations/vessel-exceptions

This endpoint requires a configured human operator credential. A vessel
integration credential cannot read it.

### Minimum-necessary projection

The human endpoint never forwards arbitrary integration payload dictionaries.
It recognizes only the Maritime Runtime v0.0.78 lifecycle contract:

    category = crew_operational_exception
    privacy_minimized = true
    advisory_only = true
    execution_authorized = false

and the explicit lifecycle mapping:

    crew.exception.opened             -> open
    crew.attention.acknowledged       -> acknowledged
    crew.attention.claimed            -> claimed
    crew.attention.escalated          -> escalated
    crew.attention.released           -> released
    crew.exception.override_recorded  -> override_recorded
    crew.attention.resolved           -> resolved

Crew-exception evidence_refs must be empty. The endpoint rejects malformed or
spoofed lifecycle combinations and exposes only:

- vessel and optional port call;
- pseudonymous exception_ref;
- latest lifecycle state;
- server-derived risk/title/summary;
- first/latest source sequence and open/update timestamps;
- privacy-safe lifecycle state/sequence/timestamp history;
- privacy/advisory/no-actuation flags.

It does not expose actor identity, task identity, work/rest minutes, private
reason text, source-system credential metadata, integration identity, or raw
payload.

### Latest state, not alert spam

A single exception can produce several lifecycle events. The shore view groups
by exception_ref and shows one current row rather than several alerts. It keeps
only the privacy-safe state/sequence/timestamp lifecycle history needed to
explain that current row.

Source sequence, not wall-clock arrival order, determines lifecycle ordering.
Impossible transitions, duplicate/non-increasing positions, state after terminal
resolution, malformed references, crew evidence refs, and non-v0.0.78 event
types fail closed and are omitted from the human view.

### Operator UI

The existing PortFlow web application adds a Vessel Exceptions panel using the
existing human operator session. It does not receive or store the vessel
integration credential.

The panel shows:

- active/resolved lifecycle state;
- vessel and port-call context;
- source sequence and time;
- pseudonymous vessel-safe exception reference;
- explicit PRIVACY MINIMIZED / ADVISORY / NO ACTUATION boundary.

No new recovery or equipment authority is introduced.

### Cross-repository contract proof

A fresh proof used current Maritime Runtime v0.0.78 code to generate the real
five-state exception lifecycle and validated every event against the current
PortFlow vessel-event model and v0.16 reduced projection.

Observed states:

    open
    acknowledged
    claimed
    override_recorded
    resolved

The proof confirmed one stable exception_ref, empty crew evidence refs,
PortFlow acceptance of the real wire model, latest-state collapse to resolved,
and absence of unique crew-private task/override/resolution sentinel strings.

This is the first KRATIA Maritime worker-to-shore vertical slice:

    local operational evidence
      -> human-owned vessel exception
      -> reason-bound local decision
      -> privacy-minimized queued shore lifecycle
      -> human-readable shore state

It remains advisory. Physical execution remains outside PortFlow.

### v0.16 verification

Exact feature tree verification before release:

- API package version: 0.16.0;
- web package version: 0.16.0;
- Docker image default tag: v0.16.0;
- full API suite: 104 passing;
- focused human vessel-exception contract suite: 3 passing;
- production TypeScript/Vite build: PASS;
- Playwright browser E2E suite: 6/6 passing, including the privacy-minimized vessel exception shore panel;
- npm production audit: 0 vulnerabilities;
- development and production Docker Compose config rendering: PASS with
  non-secret required-variable proof values;
- git diff/whitespace check: PASS.

Fresh cross-repository contract proof used current Maritime Runtime v0.0.78
code, not a hand-authored lifecycle fixture:

    MARITIME_V078_LIFECYCLE_STATES=open,acknowledged,claimed,override_recorded,resolved
    PORTFLOW_CURRENT_MODEL_ACCEPTS_REAL_V078_WIRE=PASS
    PORTFLOW_LATEST_STATE_COLLAPSE=resolved
    CROSS_REPO_PRIVATE_SENTINELS_ABSENT=PASS
    CROSS_REPO_CONTRACT_PROOF=PASS

The proof confirmed that one pseudonymous exception_ref survives the full local
human lifecycle, crew-private evidence_refs remain empty, and unique private
task/override/resolution sentinel strings never cross the Maritime Runtime wire
boundary.

The human endpoint's own API tests separately prove the authority boundary:
missing human authentication returns 401, a machine integration credential
returns 401, and a configured human viewer can inspect only the reduced
privacy-safe lifecycle view.

Physical execution remains outside PortFlow.


## v0.16.1 vessel exception hardening

v0.16.1 hardens the v0.16 human shore view without changing the Maritime
Runtime wire contract or adding authority.

### Collision-safe aggregation

The reduced shore view now scopes opaque exception references by vessel. A
matching exception_ref on two different vessels is treated as two independent
lifecycles. Within one vessel/ref scope, events must originate from exactly one
machine integration identity; conflicting producers fail closed instead of
being merged or duplicated.

### Bounded lifecycle history

The shore projection accepts at most 64 privacy-safe lifecycle transitions for
one exception. An oversized lifecycle is omitted instead of overflowing the
response model and producing a server error. Existing monotonic source-sequence
and transition validation remains mandatory.

### Visible provenance trail

The Vessel Exceptions panel now renders the ordered reduced lifecycle directly
on the card, including state and source sequence, for example:

    OPEN #1200 -> ACKNOWLEDGED #1201 -> CLAIMED #1202 -> RESOLVED #1203

The trail is built only from already-reduced shore-safe history. It does not
add crew identity, task identity, reasons, duty evidence, ledger hashes, or
machine credentials to the browser model.

The endpoint remains human-authenticated, read-only, privacy-minimized,
advisory-only, and non-actuating.

### v0.16.1 verification

Patch-candidate evidence:

- API package version: 0.16.1;
- web package version: 0.16.1;
- Docker image default tag: v0.16.1;
- full API suite: 106 passing;
- production TypeScript/Vite build: PASS;
- Playwright Chromium E2E suite: 6/6 passing;
- vessel-exception E2E visibly renders the ordered shore-safe lifecycle trail;
- npm production audit: 0 vulnerabilities;
- development and production Docker Compose config rendering: PASS with
  non-secret required-variable proof values;
- git diff/whitespace check: PASS.

Fresh cross-repository proof used the exact Maritime Runtime v0.0.78 release
tree. A temporary deployment fixture changed only the configured vessel ID to
PortFlow's synthetic `v-aurora`; Runtime behavior and projected payloads were
otherwise generated by the release code path.

Observed proof:

    MRT_V078_REAL_WIRE_GENERATION=PASS
    MRT_V078_EVENT_COUNT=5
    MRT_V078_STATES=open,acknowledged,claimed,override_recorded,resolved
    MRT_V078_PRIVATE_FIELDS_EXPOSED=false
    PORTFLOW_V0161_ACCEPTS_REAL_MRT_V078_WIRE=PASS
    PORTFLOW_VERSION=0.16.1
    PORTFLOW_HUMAN_AUTH_REQUIRED=true
    PORTFLOW_MACHINE_TOKEN_HUMAN_VIEW=false
    PORTFLOW_COLLAPSED_EXCEPTION_COUNT=1
    PORTFLOW_LATEST_STATE=resolved
    PORTFLOW_HISTORY=open,acknowledged,claimed,override_recorded,resolved
    PORTFLOW_PRIVATE_FIELDS_EXPOSED=false
    CROSS_REPO_V0161_PROOF=PASS

This patch does not add shore-side crew control, statutory compliance authority,
or physical actuation.
