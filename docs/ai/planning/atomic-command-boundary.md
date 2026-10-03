# Atomic command boundary — single-runtime milestone

Scope: continue the approved production-gate programme locally, preserving the
existing simulator semantics and stored evidence. No deployment or real delivery.

1. Reproduce callback/final-commit/reset partial writes and concurrent read/apply.
2. Add a context-local OperationsStore unit of work. Existing standalone store
   calls still commit; command callbacks share one session and flush, not commit.
3. Add one runtime-wide synchronous lock and exact mutable-state checkpoint.
   Roll back memory (including RNG/history/ticks and simulator replacement) when
   persistence fails. Detach returned DTOs before releasing the lock.
4. Route API mutations, evidence-producing proposal queries and background ticks
   through that boundary. Serialize readers/WS snapshots without awaiting while
   holding the thread lock. Preserve committed stale-contingency evidence.
5. Fault-injection + concurrency regressions, full API suite, existing browser
   workflows and explicit limitations.

Boundary: one in-process runtime. Multi-worker/process coordination, durable
command idempotency, real transport delivery, tenant authorization and distributed
recovery are not solved by a thread lock. They remain release gates. No claim of
exactly-once remote execution or crash-ambiguity resolution is permitted.

Implementation: complete for the single-runtime boundary. Final regression counts
are recorded in `docs/ATOMIC_COMMAND_VERIFICATION.md`.

Decisions:

- Keep callbacks and domain semantics; introduce a store unit of work instead of
  duplicating the simulator's event/outbox logic in a second engine.
- Reject nested command transactions explicitly. No current command calls another
  decorated command; simulator callbacks participate in the existing session.
- Commit expected stale-planning evidence, then raise its 409 outside the
  transaction. Any persistence failure still rolls back that planning attempt.
- Preserve returned response models by deep copy while the lock is held; lock
  ownership never crosses an async network await.
- One originally proposed fault case assumed recovery calls the incident sink;
  source inspection disproved that assumption. It was replaced with an incident
  creation rollback test which actually exercises that sink.
- Independent review found cancellation could abandon a running tick thread.
  A failing lifecycle regression reproduced it, followed by cancellation-safe
  joining of startup/tick/shutdown work.
- Do not claim cross-process coordination or a known outcome after an ambiguous
  database connection failure at commit. Those require a separate durable protocol.
