# Shorefront operational delivery ledger

Baseline: `943ee5c`, clean `feat/shorefront-identity`. API baseline: 173 passed (4 existing deprecation warnings), 2026-10-04.

## Rulings

- User's continuous-execution instruction overrides routine spec/plan/worktree-choice pauses. Work in the existing approved clean feature checkout; no extra worktree, no unrelated changes.
- Earlier implementation was local. On continuation, current collaboration instructions authorized bounded parallel backend/operations work and an independent read-only review. Service usage limits interrupted the agents. Their files and returned findings were checked locally; final review is self-review, not a completed independent review. No external deployment actions were delegated.
- Preserve the simulator in explicit training mode. Build operational storage beside, never reinterpret synthetic history as real facts. Cost: two mode-specific surfaces until remaining planning features are integrated safely.
- Existing palette/fonts are authoritative; do not run brand discovery or telemetry from frontend guidance.

## Programme status

| Subsystem | Current verified state |
| --- | --- |
| Operational accounts/workspace | Implemented: empty dedicated installation, accounts, invitations, revocation, password change/recovery, typed records, atomic JSON import; current verification below |
| Typed operational graph/history | Implemented typed references, derived relationship graph and effective/knowledge-time reconstruction; not a general semantic reconciliation engine |
| Commitment/recipient handoff workflow | Implemented installation-member transition rules, acknowledgement and proof; no external partner acknowledgement |
| Trust envelopes/decision packets/historical comparison | Implemented immutable recorded-input packets, deterministic schedule options, supervisor approval, explicit uncalibrated warnings; no historical counterfactual twin |
| Partner projection/federated identity | Not yet delivered |
| Standards adapters/schema registry | Not yet delivered |
| Distributed reconciliation/signed evidence | Not yet delivered |
| Commercial obligations/outcome learning | Implemented reviewed obligation states and observed outcome deviations; no legal interpretation, predictive learning or causal savings claim |
| Production deployment/customer validation | Not verified |

The training application's existing tests are not evidence that these new subsystems work.

## Verification checkpoint, 2026-10-04

- Operational browser suite: **8 passed** against the built frontend and real isolated SQLite API. Covers bootstrap/edit/history/logout, desktop light/mobile dark persistence, invitation/supervisor approval/observed outcome/reload, offline logout lock, JSON import/password rotation, malformed import/open-form offline protection, incident/assigned task/completion/history, and a delayed password response after sign-out.
- `npm run build`: passed, with the existing training map chunk-size warning. `npm run typecheck`: passed. `npm run test:config`: 1 passed.
- Browser regression evidence: missing import control failed before implementation; open editor Save remained enabled offline before the writable-state fix. Outcome inputs were absent before the observed-outcome UI was added.
- Desktop light and 375px mobile dark screenshots inspected. This is not an exhaustive accessibility or cross-engine acceptance claim.
- Full API suite with `SF_TEST_POSTGRES_URL`: **236 passed**, four existing dependency deprecation warnings. This includes real PostgreSQL concurrent writes, dump/restore into a separate generated schema, identical exported evidence after restore, and wrong-owner rejection. No test was skipped in this run.
- Original built training browser suite: **31 passed** on the final build, with results saved in `.artifacts/operational-2026-10-04/training-browser.log`.
- Bootstrap deadline persistence/reopening, schema compatibility, local password recovery and restore overlay/failure behavior passed in the full API run. Restore-script command tests substitute Docker; the real PostgreSQL test is a separate isolated schema-level rehearsal, not a customer deployment rehearsal.
- Full independent review was interrupted by service usage limits. A separate local self-review completed; this is weaker than independent approval and does not satisfy the customer release review gate.
- No live customer database was modified. No production deployment or main-branch merge is part of this checkpoint.

## Review corrections and decisions

- Open record editors now receive current write authority, disabling Save offline while retaining input. Browser test failed before the fix and passed afterward.
- Late password-change responses cannot restore a session after logout or a different session generation. A held real HTTP response reproduced the failure before the guard; the final browser suite passes.
- The migrator rejects an unknown runtime instead of selecting training. Regression failed before normalization/validation and passes in the full suite.
- Outcome revisions use server knowledge time; actual event times remain in the payload. Outcome-to-decision association is immutable, preventing rescheduling or retargeting a single measurement to inflate/reassign results. Regressions failed before the restrictions and now pass.
- Approval verifies stored evidence against the audit before applying a plan. A deliberately altered test packet previously passed approval; it now returns conflict without changing records. This remains an ordinary-corruption checksum check, not signed evidence or protection against an administrator rewriting the whole database.
- Keep the training app and customer app explicitly separate. No legacy synthetic record is reinterpreted as a customer observation. Cost: two runtime surfaces remain to maintain.
- Keep the approved brand and existing feature checkout. No new visual identity, provider credential, paid service or unrelated project is introduced.

## Open release and programme gates

- Dedicated customer host/origin/secrets, trusted TLS, target-specific backup/restore, monitoring and customer operational acceptance are not verified. `production_ready` remains false.
- Independent complete security/code review, cross-engine browser testing, load/concurrency capacity and storage-retention limits remain release gates. All store transactions currently serialize; history/evidence growth is not performance-qualified.
- The first decision-list view is bounded to 100 packets (API accepts a larger limit up to 500); a complete historical decision navigation/search surface remains to be delivered. Do not interpret the displayed set as exhaustive history. All packets remain in exported evidence.
- Partner resource/field projections, federated identity, standards-conformant live connectors and SDK registry, semantic source reconciliation, counterproposal chains, historical counterfactual twin, external signatures/timestamps, offline reconciliation and calibrated outcome learning remain separate unfinished subsystems.
- No live AIS/weather entitlement, external recipient acknowledgement, navigational clearance, contractual interpretation, cash receipt, causal savings or automated claims submission is implied.
- Minor presentation follow-ups: mobile navigation wraps Team to a second row; the training map retains a large-chunk build warning. No all-viewport/accessibility-complete claim is made.

Use [the operational runbook](OPERATIONAL_RUNBOOK.md) for installation and recovery. API run evidence is saved locally under `.artifacts/operational-2026-10-04/api-tests.log`; browser screenshots are regenerated under `apps/web/test-results/` and are disposable test artifacts, not customer data.

## Converged operational dashboard checkpoint — 2026-10-04

- Branch `feat/shorefront-v2-convergence` combines the authenticated operational core with the dense Shorefront control interface instead of maintaining a separate visually rich demo-only product.
- Operational Pulse now derives active calls, incidents, tasks, incomplete handoffs, obligations and resource pressure only from durable customer records. Unknown facts remain unknown.
- Plan renders real berth/call windows and resource availability from operational records; it does not invent quay geometry, weather or schedule mutations.
- Calls ties each recorded call to its incidents, tasks, commitments, handoffs and obligations. Exceptions provides a record-derived action inbox. Existing evidence-bound decision packets remain available from Plan and Recovery.
- Initial administrator setup supports a one-time URL-fragment setup link; the browser consumes the token client-side and removes it from the address bar. Manual setup-token entry remains as recovery fallback.
- Verification on this checkpoint: API `235 passed, 1 skipped`; runtime config PASS; TypeScript and production build PASS; operational browser `8/8`; training browser `31/31`.
- This does not change the documented unfinished infrastructure gates or set `production_ready=true`.

## Actionable workspaces source checkpoint — 2026-10-04

The owner explicitly requested committing all pending Shorefront work before resolving
the generated-directory ownership blocker. This is a source checkpoint, not a verified
release, main-branch merge or deployment.

- Added a server-derived coordination action projection and a dedicated desk for
  handoffs, commitments and reviewed obligations. Writes still use the existing
  authenticated, revision-checked and audited record command.
- Added contextual record editors, call-linked incident/task creation, actionable
  attention queues, a first-call setup guide and recorded schedule-conflict display.
- Added inspectable historical payloads, provenance, current-view comparisons and
  request-generation guards in the Evidence workspace.
- Corrected coordination assignment to read-only members, cancellation after recipient
  revocation, full-precision due-time equivalence and preservation of reviewed obligation
  terms. The active obligation review note may be corrected; its underlying terms remain
  sealed. Unchanged timestamps are preserved by record and transition forms.
- Fresh commit-time checks: `npm run typecheck` passed; `uv run --frozen pytest
  tests/test_product_workflows.py -q` passed **14 tests**, with two existing dependency
  warnings; `git diff --check` passed. The preceding combined product API run passed
  **60 tests**. The full baseline before this batch was **235 passed, 1 skipped**
  (PostgreSQL test URL absent), not a full-suite verification of this new batch.
- New browser regressions were observed failing against the earlier UI. Their final
  passing run, visual inspection and full training regression run are **still pending**.
- The frontend build failed with `EACCES` while replacing the root-owned
  `apps/web/dist/assets` directory. `apps/web/test-results` is also root-owned.
  No ownership changes were made. Separate temporary output paths were used for
  diagnostic browser runs without altering the protected artifacts.
- Parallel assistance was interrupted by service usage limits; no completed independent
  review is claimed. The current source still retains the superseded read-only
  `ProductOperations.tsx` and inline Evidence/Pulse definitions for later cleanup.
- A separately identified unresolved case remains: a scheduled/backdated highest
  revision can differ from the current effective snapshot revision, leaving the generic
  editor unable to resolve a revision conflict through refresh alone. Do not silently
  alter the two-clock semantics to hide this case.

Plan and acceptance details: [actionable workspaces plan](superpowers/plans/2026-10-04-actionable-workspaces.md).
All broader programme and production gates above remain open where stated.
