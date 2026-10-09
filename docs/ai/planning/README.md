# Shorefront implementation queue

## Immediate milestone

- [x] Engine-backed read-only comparison and isolated guided-demo API (two API tests).
- [x] Focused workspaces, attention-first Pulse/mobile and presentation role lens.
- [x] Guided demonstration, comparison timelines, contextual evidence, architecture.
- [x] Bounded initial loading/retry, stale-state protection and lifecycle cleanup.
- [x] Canonical active identity and explicit legacy compatibility inventory.
- [x] Fresh API, TypeScript, build and dev/built browser regression evidence.

## Operational programme — reconciled 2026-10-05

The original queue mixed the training runtime with operational work added later.
The following separates implemented subsets from genuinely open acceptance gates.
Checked subsets do not close the larger programme.

| Area | Implemented and covered by current tests | Still open |
| --- | --- | --- |
| Authority and commands | Dedicated installation ownership, roles, transactional record/audit/idempotency writes, SQLite write serialization and PostgreSQL advisory transaction locking; concurrent-write and restore tests | Multi-process/crash/load qualification, durable external outbox delivery and full authority review |
| Knowledge and time | Typed record graph, recorded/effective-time reconstruction, version conflicts and explicit editor recovery | Generalized semantic reconciliation and historical counterfactual decision replay |
| Decisions and evidence | Immutable recorded-input packets, bounded searchable history, supervisor approval, hash-chain export and standalone offline consistency checker | Externally signed evidence, key custody/timestamps and independently qualified trust policy |
| Coordination | Versioned commitments, internal handoffs with named recipient acknowledgement, reviewed obligations and descriptive outcomes | Partner counterproposals/federation, validated claims workflow and calibrated causal learning |
| Identity and policies | Dedicated database owner, accounts, session revocation and backend role checks | Cross-organisation identity, resource/field projections and projection firewall |
| Integrations | Existing training adapters; validated operational record entry/import | Operational DCSA/S-211 conformance, schema registry/SDK, licensed feeds, durable delivery receipts and reconciliation |
| Release | Isolated PostgreSQL restore tests, built browser workflows, existing local Docker/quick-tunnel installation | Durable customer hosting, automated retention/monitoring, independent security, cross-engine/accessibility/load and customer acceptance |

Evidence and exact limitations: [operational status](../../OPERATIONAL_PRODUCT_STATUS.md),
[completion pass](../../COMPLETION_PASS_2026_10_05.md), and
[offline evidence verification](../../EVIDENCE_VERIFICATION.md).

Implementation starts with visible, verifiable operations. No phase is complete
merely because its route, design document or placeholder exists.

## Decisions and review fixes

- Retained the existing approved feature checkout; unrelated work is preserved.
  The original milestone did not itself imply delivery. Subsequent verified
  commits and deployment receipts are recorded in the operational status ledger;
  no main-branch merge or complete commercial qualification is implied.
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
