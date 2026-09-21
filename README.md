# PortFlow

PortFlow is a port-call operations control tower for continuously updated vessel, berth, weather, incident, delay, connectivity, and schedule state.

## Status

Private portfolio build, v0.11 resilient live-adapter state + last-known-good preview boundary.

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

## Next engineering milestone

v0.12 should focus on deeper capacity modeling, cross-resource recovery, and deployment:

- richer crane/cargo multi-resource capacity constraints
- cross-resource recovery optimization across multiple incident classes
- adapter freshness impact on decision confidence
- retry/backoff scheduling beyond on-demand snapshot requests
- richer crane/cargo multi-resource capacity constraints
- cross-resource recovery optimization across multiple incident classes
- optional OIDC-compatible production identity adapter
- hosted portfolio deployment with a real public demo
