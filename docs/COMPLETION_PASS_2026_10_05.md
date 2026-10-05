# Shorefront completion pass — 2026-10-05

Starting application source: `97c463d`, retaining the owner's newer coordination
visuals. Work remains on `feat/shorefront-v2-convergence` per the established
checkout preference. The untracked `.live-coordination-audit.mjs` is unrelated
work and is not edited, executed or committed by this pass.

## Intended acceptance and current work

- Correct the public showcase's reused operational-mode label. Keep the private
  workspace label and all data-access boundaries unchanged. Browser regression
  observed the misleading label before the fix.
- Make every decision packet reachable through bounded 25-item UI pages and
  server-side question/call-ID/packet-ID search plus approval-state filters.
  Keep the existing array API/default limit and immutable packet bytes. No
  schema migration. Order is packet ID, explicitly not chronological; refresh
  restarts navigation to include concurrent additions. A failed page retains
  the last verified page and exposes retry; request generations reject stale
  responses. Tests traverse 103 packets, literal wildcard queries and both SQL
  dialects. This is not a transactionally frozen cross-page snapshot.
- Add standalone, offline evidence consistency verification with installation
  matching and optional separately retained root pinning. Reject changed,
  missing and duplicate records/decisions, broken chains and changed approvals.
  Do not claim signatures, external timestamps or real-world truth.
- Remove unreferenced `ProductOperations.tsx` and superseded inline Pulse/Evidence
  definitions. These are recoverable from Git; live workspaces are retained.
- Synchronize the initial hash route when installing the navigation listener.
  The browser regression reproduced `#recovery` displaying Pulse when navigation
  happened between initial render and effect registration; it passed after the
  listener also consumed the current hash on mount.
- Reconcile stale programme checkboxes with actual code and test evidence.

## Scope rulings

- Continuous implementation, commit and push are explicitly requested. No routine
  design pause or extra worktree is introduced. New customer integrations,
  federated access grants, purchases, legal/financial actions and new hosting
  accounts are not inferred from that instruction.
- The requested ownership repair changes only the two named root-owned showcase
  files. Previously approved generated `dist`/`test-results` ownership repair
  was repeated after another process recreated them. No wider source, home or
  database ownership change.
- After the commit was blocked by root-owned Git metadata, the user explicitly
  approved the repair. Ownership was changed to `nur:nur` only for the nine named
  object directories, Git index and current feature-branch reference. No recursive
  source repair or permission widening was performed.
- The read-only census completed; the attempted delegated backend implementation
  hit service usage limits before changes. Implementation and final review are
  local unless a later completed review is explicitly recorded.
- Existing customer operations are not test fixtures. Browser and API tests use
  isolated databases; no operational record is seeded into the live installation.

## Programme remains open

The source has dedicated-installation accounts, versioned records, a typed graph,
two-clock reconstruction, database-arbitrated atomic/idempotent commands, internal
handoffs/commitments/obligations, recorded-input decision packets and descriptive
outcomes. Old blanket unchecked entries do not accurately describe those pieces.

Still missing: partner field/resource projections and federated identity;
operational standards-conformant ingestion, durable external delivery/receipts and
reconciliation; generalized source-semantic reconciliation; externally signed
evidence/key custody; historical counterfactual decision runs; calibrated learning;
durable customer hosting, automated retention/monitoring, performance and full
independent security/accessibility/cross-engine/customer acceptance.

These are actual unfinished subsystems, not renamed completed work. Some require
external contracts, entitlements, data or target decisions; others require further
implementation. `production_ready` remains false.

## Verification and delivery

| Executed check | Result |
| --- | --- |
| Full API suite, including isolated PostgreSQL | 278 passed, no skips; four existing dependency warnings |
| Built operational browser suite | 19 passed |
| Built training browser suite | 31 passed |
| TypeScript and production build | Passed; existing lazy training-map size warning remains |
| Runtime configuration test | 1 passed |
| npm production-dependency audit | Zero findings |
| 103-packet navigation, failed loads and delayed-response browser regressions | All three passed; included in the 19 above |
| Fresh deployed-database backup restored to separate PostgreSQL database | Passed; owner/schema verified, offline root-pinned verification passed, evidence digest matches live |

The API list and showcase regressions were observed failing before implementation.
The standalone verifier initially failed with the missing module; its 13 checks
now pass, including altered/missing records, options, approvals, audit chain,
installation, root and duplicate JSON keys. Those checks are part of the 278,
not additional tests. The startup navigation failure was reproduced twice and
passed after current-hash synchronization.

The 375px decision-history screenshot was visually inspected; the complete suite
also retains existing coastal light/dark and viewport checks. These are Chromium
checks, not full cross-engine/accessibility qualification. Logs and browser
artifacts are local and ignored under `.artifacts/completion-2026-10-05/`.

Pre-update live application: `97c463d`. Installation evidence remains sparse
(zero factual versions and decisions), so the live backup rehearsal is not a
populated customer acceptance test. Populated workflows and concurrent writes
are exercised in isolated fixtures. The private backup is mode 0600 and is not
published. No customer records, account credentials or approvals were created
for live verification.

## Live delivery follow-up: stale browser shell

Application `c25bb273bab6b3541e050c47a1b5a1c318a52604` was committed, pushed and
deployed to the existing installation. API/web health, source hashes, public HTML
hash and preserved database evidence passed. A previously opened browser tab,
however, reused the old HTML and old bundle: the server supplied the new release
while the browser still showed the old showcase boundary. The HTML had no explicit
cache policy, allowing heuristic freshness. This was a delivery defect, not a
successful browser acceptance result.

- Both Nginx configurations now require revalidation for `/index.html` (including
  root, showcase-query and SPA fallback requests) and `/theme-init.js`.
- The policy leaves upstream API and content-hashed asset headers unchanged.
  Existing security headers are preserved; unchanged shells can still return 304.
- `SHOREFRONT_TEST_WEB_IMAGE=shorefront-web:operational-c25bb27 npm run test:delivery`
  launches disposable loopback-only HTTP/TLS test endpoints from a prebuilt local
  image with the checkout configuration mounted read-only. It uses no customer
  data, deployment network or credentials, pulls no images, and removes its own
  containers and generated test certificate afterwards.
- Both real-Nginx tests failed before the configuration change because the header
  was missing, then passed after it. They cover root, showcase, direct index,
  fallback, theme bootstrap, conditional 304 and security-header preservation.
- A page cached before this fix may require one hard refresh. The new header
  cannot retroactively invalidate a response already considered fresh by a client.

Final delivery hashes and post-update checks are recorded below after deployment.
