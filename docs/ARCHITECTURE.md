# Shorefront architecture

Shorefront is a maritime operational decision, coordination and evidence layer.
It is a standalone, advisory-only prototype. It does not actuate vessels, replace
a terminal operating system, decide legal obligations or claim certified standards
conformance.

## Current decision path

```text
Configured/fixture signals → canonical harbor state → dependencies and exceptions
                         → recovery projections → human approval → stored receipt
```

`apps/api/src/shorefront_api/simulator.py` owns operational semantics. React must
not independently calculate recovery actions. REST and WebSocket snapshots expose
the harbor picture. `OperationsStore` uses SQLite or PostgreSQL for the current
snapshot, incidents, events, proposals, scenario evidence and receipts.

## Workspaces

Pulse answers what needs attention. Plan holds map, berths and resources. Calls
shows service dependencies. Exceptions exposes operational and vessel exceptions.
Recovery compares projected schedules and retains authenticated approval. Evidence
shows source provenance and recorded events. Full control tower is an optional
advanced view, not the default mobile experience.

Role lenses affect presentation only. Existing configured operator identities and
backend role checks determine actual approval authority.

## Isolated projections

`GET /api/v1/recovery/comparison` clones a snapshot into sink-free simulators and
returns the current and projected schedules. It does not reserve resources, apply
changes or write evidence. `GET /api/v1/demo/story` uses a new isolated simulator
to compute a tug disruption and its recovery. The simulated receipt identifies a
simulated actor and is never stored as an authenticated operational decision.

## Transport and trust

The frontend bounds initial snapshot fetches through response-body consumption,
validates nested snapshot fields, rejects older snapshots, cleans up reconnect
timers and marks stale/disconnected pictures read-only. Source freshness and
snapshot transport freshness are different signals and remain distinguishable.
Malformed comparison/story responses expose retry instead of entering render state.
Invalid stream data retains the last usable picture; reopening a socket alone
does not re-enable mutations. Ending a local operator session works offline.

The simulator supplies `decision_revision`, a stable invalidation key derived
from its canonical recovery fingerprint plus calibration and display provenance.
Both comparison and proposal queries follow that revision, including resource-only
or provenance-only changes. Volatile snapshot clocks do not cause repeated aborts.
This key is not an authorization token or a tamper-evidence signature. Old records
without it serialize unchanged, preserving their existing evidence digests.

Shared reset/scenario/connectivity/replay controls require the explicit
`SHOREFRONT_DEMO_CONTROLS=1` opt-in and are intended for disposable demo databases.
The isolated guided story remains available without the flag. Incident mutations
require an authenticated operator/supervisor when demo controls are disabled.

Modeled exposure is not revenue or verified savings. Evidence health is not a
calibrated success probability. Outbound queue replay currently models delivery;
it does not prove an external receiver accepted a message.

## Production gates and future architecture

API mutations, evidence-producing planning queries and simulator ticks now share
one single-process command boundary. Store callbacks use one SQLAlchemy transaction;
intermediate writes flush without independently committing. A runtime-wide lock
serializes commands/readers, and exact checkpoints restore mutable state on failed
writes/commit, including RNG, proposal history and simulator replacement. Responses
are detached before releasing the lock. Worker cancellation waits for an in-flight
transaction before returning from shutdown. Successful-command metrics are deferred
until after commit. Stale proposals remain a committed planning/evidence outcome
with a 409 response, not an approval.

This is **not** distributed writer coordination: use one API worker and one runtime
per database. Multi-process enforcement, ambiguous commit reconciliation, durable
command idempotency and live PostgreSQL failure/restore acceptance remain open.
Direct callers of the low-level simulator do not acquire the API boundary unless
they explicitly use it; standalone storage calls retain their old commit behavior.

Other open gates include consistent operational authorization, tenant boundaries, real integration contracts and
delivery acknowledgements. The broader approved programme adds bitemporal facts,
operational/commitment/obligation graphs, decision packets, projection policies,
standards gateways and outcome calibration. Those are not represented as shipped.

The current descriptive event ledger is not sufficient for faithful historical
reconstruction. No historical view may infer what an operator knew using facts
received later. No standards badge may precede version-specific conformance tests.

## Compatibility and provenance

See [the migration guide](RENAMING_AND_UPGRADING.md) for preserved legacy wire
identifiers, database discovery, environment aliases and evidence formats. They
are technical compatibility boundaries, not active product identity.

The [historical architecture baseline](history/architecture-baseline.md) is kept
as source provenance; its claims and paths do not define the current product.
See [implementation progress](ai/planning/README.md) and
[verification record](ai/testing/README.md) for the active work.
