# Shorefront implementation queue

## Immediate milestone

- [x] Engine-backed read-only comparison and isolated guided-demo API (two API tests).
- [x] Focused workspaces, attention-first Pulse/mobile and presentation role lens.
- [x] Guided demonstration, comparison timelines, contextual evidence, architecture.
- [x] Bounded initial loading/retry, stale-state protection and lifecycle cleanup.
- [x] Canonical active identity and explicit legacy compatibility inventory.
- [x] Fresh API, TypeScript, build and dev/built browser regression evidence.

## Remaining programme (not shipped)

- [ ] Consistent operational authority, atomic state/receipt/event/outbox commits.
  - [x] Single-process API command transaction, exact rollback, reader serialization,
    response detachment and cancellation-safe worker shutdown.
  - [ ] Multi-process writer ownership, ambiguous-commit recovery, durable command
    idempotency, live PostgreSQL acceptance and complete authority closure.
- [ ] Operational knowledge graph and semantic conflicts.
- [ ] Persisted bitemporal history and historical counterfactual replay.
- [ ] Universal decision packets, trust envelopes and tamper-evident evidence.
- [ ] Versioned commitment graph; DCSA conformance; experimental S-211 mapping.
- [ ] Organisation identity, backend scoped policies and projection firewall.
- [ ] Schema registry, adapter SDK, real delivery acknowledgements/reconciliation.
- [ ] Reviewed obligation/handoff module; claims workspace after validation.
- [ ] Outcome calibration, licensed feeds and production recovery/release gates.

Implementation starts with visible, verifiable operations. No phase is complete
merely because its route, design document or placeholder exists.

## Decisions and review fixes

- Retained the existing approved, dirty feature checkout; unrelated design work
  was preserved. No commit, push, merge or deployment is implied.
- Preserved published legacy contracts and old evidence rather than replacing
  their bytes. A versioned consumer migration remains necessary to retire them.
- Used an engine-derived revision for recovery invalidation, rather than
  duplicating feasibility inputs in React. Legacy absent revisions stay omitted
  on serialization so historical evidence hashes are not changed.
- Independent read-only review found stale comparison invalidation, offline
  logout blocking and insufficient nested transport validation. Each received a
  regression test and a fix. Review was scoped to this milestone, not a production
  audit of the unimplemented programme.
- No telemetry, external analytics, paid service or live credential changes were
  needed for the frontend-design checks.
