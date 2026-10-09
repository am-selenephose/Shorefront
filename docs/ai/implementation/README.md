# Shorefront implementation record

2026-10-03: Read both supplied documents in full; confirmed existing dirty design
work on `feat/shorefront-identity` and preserved it. The documentation preflight
reported missing lifecycle files; these five files provide the approved project
record without introducing unrelated scaffolding.

No deployment, push, paid service, live credential change or memory write is part
of this work. Fresh verification results will be recorded here and in testing.

Read-only comparison and story endpoints now use sink-free simulator instances.
Comparisons include full projected schedules from the same engine as proposals.
Demo receipts identify a simulated operator; no global state or store is attached.
The optional task read probe failed: `task` is not a command in the installed
ai-devkit release. Markdown files are the progress record; no task events invented.

The app now mounts focused Pulse / Plan / Calls / Exceptions / Recovery / Evidence
workspaces, with full control tower available separately. Guided demo and
architecture are presentation modes; role lenses never grant authority. New views
reuse the approved coastal tokens and local fonts in both themes.

`useHarborStream` owns the initial fetch deadline, socket/reconnect lifecycle and
last usable picture. Runtime transport guards reject malformed nested inputs.
Comparison and story loaders validate before committing render state and expose
retry. Initial failure, silent/stale sockets and invalid reconnects are explicit
read-only states. Offline logout remains available.

The simulator's additive `decision_revision` invalidates comparison and proposal
queries for canonical resource/schedule/provenance changes without refreshing on
every wall-clock tick. Old evidence omits an absent revision, preserving its
original digest. Full API regression caught and protected that boundary.

Runtime capabilities expose the explicit shared-demo mutation flag (default off).
The isolated story works without it. Browser tests use separate temporary SQLite
databases and test-only credentials; no real operational database is reset.

The broad commercial infrastructure programme is still open in the planning
record. Local validation does not establish production, customer or financial
outcomes. See the testing record for fresh counts and evidence paths.

Follow-on: the approved atomicity gate now has a single-runtime implementation.
`operations.py` owns synchronous command/query serialization and rollback;
`OperationsStore.transaction()` supplies one session across existing callback
writes and dependent reads. API mutations/planning and ticks participate. Reset
and scenario failures restore the old simulator pointer as well as durable rows.
Returned models are detached, stale-planning evidence stays compatible, diagnostic
success counters run after commit, and async cancellation cannot abandon a worker
still inside a state operation. See the atomic-command plan and verification report
for tests and remaining multi-process/production limits.
