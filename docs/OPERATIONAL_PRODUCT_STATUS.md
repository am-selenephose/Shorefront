# Shorefront operational delivery ledger

Baseline: `943ee5c`, clean `feat/shorefront-identity`. API baseline: 173 passed (4 existing deprecation warnings), 2026-10-04.

## Rulings

- User's continuous-execution instruction overrides routine spec/plan/worktree-choice pauses. Work in the existing approved clean feature checkout; no extra worktree, no unrelated changes.
- No delegation this turn. Implementation and final review are local; this is weaker than independent review and must be stated at release.
- Preserve the simulator in explicit training mode. Build operational storage beside, never reinterpret synthetic history as real facts. Cost: two mode-specific surfaces until remaining planning features are integrated safely.
- Existing palette/fonts are authoritative; do not run brand discovery or telemetry from frontend guidance.

## Programme status

| Subsystem | Current verified state |
| --- | --- |
| Operational accounts/workspace | In progress |
| Typed operational graph/history | In progress |
| Commitment/recipient handoff workflow | Not yet delivered |
| Trust envelopes/decision packets/historical comparison | Not yet delivered |
| Partner projection/federated identity | Not yet delivered |
| Standards adapters/schema registry | Not yet delivered |
| Distributed reconciliation/signed evidence | Not yet delivered |
| Commercial obligations/outcome learning | Not yet delivered |
| Production deployment/customer validation | Not verified |

The training application's existing tests are not evidence that these new subsystems work.
