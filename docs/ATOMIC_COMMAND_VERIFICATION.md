# Shorefront atomic commands — single-runtime verification

2026-10-03. Local branch `feat/shorefront-identity`, based on `f83dec1`.
No commit/push/deployment or real operational database mutation was performed.

## What changed

Each API command now runs under one runtime lock and one SQLAlchemy transaction.
Existing callback writes and dependent reads join the same session. No receipt,
event, incident, envelope or snapshot callback commits independently within a
command. Responses are detached before releasing the lock. On a failed write or
commit, exact in-memory state is restored, including RNG/tick state, proposal
history and the original simulator pointer after a failed reset/scenario.

The boundary covers incident operations, recovery approval, calibration/adapter
ingest, vessel event intake, scenarios/reset, connectivity/replay, evidence-producing
proposal/coordination queries, initialization and simulator ticks. Read endpoints
serialize with those operations. WebSocket snapshots are captured in a worker and
detached before awaiting network delivery. Shutdown, including cancellation, joins
workers that still own operational state. Success metrics are deferred until commit.

Stale recovery remains a 409 planning result: newly calculated contingency evidence
commits without an approval receipt. Storage errors during planning still roll back.
No database schema version change or legacy evidence rewrite was needed.

## Verification

- Full API suite: **173 passed**, four dependency/migration deprecation warnings.
- New atomicity/lifecycle tests: **17**, included in that full suite.
- TypeScript and the one configuration-isolation test passed unchanged.
- Built-app Chromium suite: **31 passed** against the new backend.
- `git diff --check`: passed.

The new tests cover:

1. Recovery receipt/event/outbox/snapshot callback failure and successful retry.
2. Incident-row failure with memory and durable rollback.
3. Final commit failure, including no false successful-approval metric.
4. Failed reset and scenario-evidence writes preserving old state.
5. Replay rollback restoring pending envelopes and acknowledgements.
6. Tick failure restoring RNG, tick count, events and picture.
7. Unit-of-work read-your-writes, separate-store isolation and cleanup after errors.
8. Concurrent approval yielding one successful receipt, and readers blocking until
   an in-flight recovery has committed.
9. Vessel event and audit atomicity; retry after failure is not a false duplicate.
10. Expected stale-contingency evidence retention without an approval receipt.
11. Response detachment across in-place incident resolution.
12. Cancelled shutdown waiting for the running tick worker to finish.

Initial fault injection reproduced partial state/rows and concurrent reader/approval
failures. The shutdown test also failed before the cancellation-safe join. One
initial test incorrectly expected recovery to call the incident sink; it was
replaced by an actual incident-create fault test. Independent read-only review
checked session participation, entry points, rollback, detachment and cancellation;
the cancellation finding was fixed and covered by the final suite.

Full logs: `.artifacts/atomic-commands-2026-10-03/` in the repository root.
All database fault injection used temporary SQLite databases and test identities.

## Limits — required before commercial release

- One process, one simulator, one database owner. No distributed writer lease,
  fencing or safe multi-worker mode exists. A thread lock cannot provide it.
- Live PostgreSQL crash/failover behavior and backup/restore acceptance were not
  exercised. An ambiguous remote commit outcome still needs durable reconciliation.
- Standalone store calls still commit independently. Direct low-level simulator
  consumers must use an operation boundary to get the API guarantee.
- General durable command idempotency, tenant authorization and lifecycle policy
  are not complete; this is not a complete security certification.
- Replay still models delivery. A database transaction cannot undo an external
  side effect, and no real external delivery was introduced or certified here.
- Bitemporal history, full operational/commitment graphs, standards conformance,
  licensed integrations and outcome calibration remain separate roadmap work.

This is a verified local integrity improvement, not a final commercial release.
