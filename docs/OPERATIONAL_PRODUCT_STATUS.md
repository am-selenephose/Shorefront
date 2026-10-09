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
| Partner projection/federated identity | Scoped field/resource projections delivered; federated identity/SSO remains open |
| Standards adapters/schema registry | Generic scoped operational-record ingestion delivered; standards/vendor adapters and external schema registry remain open |
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

## Historical release and programme gates — 2026-10-04 baseline

This checkpoint is retained for provenance, not as the current backlog. The
2026-10-05 checkpoints below supersede the decision-history limitation and record
the deployed-installation backup/restore rehearsal. Current unfinished gates are
listed in [the completion pass](COMPLETION_PASS_2026_10_05.md#programme-remains-open).

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

## Public showcase checkpoint — 2026-10-04

- Added an isolated public product showcase at `/?showcase=1` for recruiters, buyers and reviewers who should not receive an operational account.
- Showcase data is static, fictional and visibly marked `SIMULATED DEMO · READ ONLY` in both the sidebar and content header.
- Showcase mode bypasses operational authentication/runtime loading and does not call private workspace, records, decision, history or coordination APIs. The browser regression test asserts zero private API traffic across Pulse, Plan, Calls, Exceptions, Recovery and Evidence.
- The showcase demonstrates berth overlap, resource loss, accountable action, coordination, recovery comparison and evidence context without inserting sample records into the operational PostgreSQL database.
- The private sign-in/setup surface now exposes `Explore Shorefront demo` while operational accounts and invitation flows remain unchanged.
- Mobile showcase and operational views are constrained to viewport width; only the workspace navigation strip scrolls horizontally.
- Regression hardening completed alongside the showcase: evidence tests scope version rows, historical replay uses valid second-precision local clock values, stale delayed replay responses remain ignored, and workflow selectors target the record editor rather than similarly named workspace filters.
- Fresh release gate: API `249 passed, 1 skipped`; runtime config PASS; TypeScript/build PASS; operational browser `13/13`; training browser `31/31`; release-gate job exit `0`.
- The existing infrastructure gaps remain unchanged and `production_ready` remains false.

## Revision-conflict and release checkpoint — 2026-10-05

This supersedes the earlier pending-browser and generic-editor conflict notes;
it does not close the unfinished commercial infrastructure programme.

- Closed the scheduled/backdated revision conflict loop with an authenticated
  latest-recorded-version read and explicit review/replace/save actions. The
  current effective snapshot and immutable history retain their original meaning.
- Closed a reviewer-found relationship-loss case: an unavailable recorded
  reference remains selected instead of becoming blank during replacement.
  The server still rejects a not-yet-effective relationship. Clearing one is an
  explicit operator action, not an automatic correction.
- Fresh full API verification with isolated PostgreSQL: **257 passed, no skips**,
  four existing dependency warnings. Built operational browser suite: **16 passed**,
  including real persistence, temporal review, offline input protection and the
  future-only relationship regression. TypeScript/production build passed;
  runtime config test passed; npm production-dependency audit found zero findings.
- The previously approved ownership repair was limited to generated frontend
  `dist` and `test-results` directories. Source and database ownership were not
  changed. No user credentials or operational records were created for testing.
- A private deployed-database backup restored successfully to isolated storage,
  with valid audit and matching exported evidence. The live installation has zero
  factual versions/decisions; this is not a populated customer acceptance rehearsal.
- A read-only independent reviewer reported the relationship-loss finding, then
  hit a service usage limit. The fix was locally reproduced and verified; no
  completed independent release/security approval is claimed.
- Final built training regression: **31 passed**. Application commit `337cbaa`
  was pushed and deployed as API/web images `operational-337cbaa`. Both services
  are healthy; the public frontend hash matches the build; the original database
  volume and evidence digest are unchanged. Read-only live workspace navigation
  passed. This is a verified update to the existing quick-tunnel installation,
  not durable commercial hosting or completion of the production gates.

Full regression evidence, rollback boundary and remaining gates:
[2026-10-05 release record](RELEASE_2026_10_05.md).

## Searchable decisions and offline verification — 2026-10-05

- Decision history now reaches all packets through bounded pages, with server-side
  literal question/call-ID/packet-ID search and pending/approved filters. This
  supersedes the earlier 100-packet navigation limitation. It is packet-ID order,
  not chronological order or a frozen multi-page snapshot.
- Failed loads preserve the last loaded page and offer retry; stale responses
  cannot replace a newer search. A startup hash-change race that could display
  Pulse at a Recovery URL is fixed and covered by the browser regression.
- The public showcase now explicitly says its operational picture is simulated.
  It remains read-only and isolated; the private workspace keeps its real-mode
  label. No data-access authority changed.
- An independent, standard-library-only offline verifier checks export consistency
  and supports a separately retained audit-root pin. It does **not** provide
  signatures, external timestamps, physical-event truth or commercial validation.
  See [verification instructions](EVIDENCE_VERIFICATION.md).
- Removed only unreferenced duplicate workspace implementations; live workspaces
  and the newer coordination visuals remain. Removed code is recoverable in Git.
- Fresh checks: **278 API tests with PostgreSQL, 19 operational browser tests,
  31 built training browser tests**, TypeScript/build and configuration test pass.
  Production npm audit found zero vulnerabilities. The private live backup restored
  with matching evidence and passed the offline verifier. These results do not
  constitute independent security approval, load testing or cross-engine QA.
- The programme queue now separates completed subsets from federation, external
  integration, signed-evidence, counterfactual/learning and durable-hosting gaps.
  `production_ready` remains false.

Exact scope, evidence, delivery and remaining work:
[completion pass](COMPLETION_PASS_2026_10_05.md).

Delivery: features `c25bb27` and entry-page cache fix `fd3f2fa` are committed and
pushed; API/web images `operational-fd3f2fa` are deployed and healthy with the
original database preserved. Two additional real-Nginx HTTP/TLS regression tests
pass. The former quick-tunnel hostname stopped resolving; the current preview is
<https://compression-ethnic-judge-determine.trycloudflare.com/>. This replacement
is still temporary, not a durable-production-hosting claim. The completion-pass
receipt records exact source/image hashes, current origin, recovery and limits.
## Advanced command UI and scoped connections checkpoint - 2026-10-06

- The operational browser is now a denser command surface: map-first Pulse, persistent desktop status rail, global record search, berth/call runway, signal bands, dense call/record/team registers, exception pressure, map-layer controls and responsive mobile layouts.
- Added an administrator-only Connections workspace. Inbound machine sources receive one-time bearer credentials, explicit writable record-kind allowlists, bounded atomic/idempotent batches, durable source attribution, usage counters, expiry, rotation and revocation. Plaintext tokens are returned only at creation/rotation; Shorefront stores digests.
- Added partner read projections with separate one-time credentials, explicit record-kind and payload-field allowlists and optional recorded-call scope. Unknown call scopes fail closed instead of broadening access. Projection output excludes raw source attribution and actor IDs.
- These connection primitives are not federated identity, vendor-specific AIS/TOS/weather connectors, a standards schema registry, durable external delivery/receipt federation or proof of third-party acceptance. Those remain separate work. production_ready remains false.
- Fresh full gate: 288 API tests with isolated PostgreSQL and no skips, 21 operational browser tests, 31 training browser tests, runtime-config 1 passed, delivery-cache/TLS 2 passed, production build passed and npm production audit reported zero vulnerabilities.
- Live-database migration was rehearsed against a restored backup and then applied additively. All pre-existing operational counts remained unchanged; sf_connection_source and sf_partner_grant were added empty. PostgreSQL container identity, start time and volume remained unchanged across migration and API/web cutover.
- Deployed application source is GitHub commit d9ee49a0998dc41965397d8571e57a96cf918f2a, verified source tree 8399d60c9152645a76f5c0f5599c07717a7152fe, image tag operational-d9ee49a.
