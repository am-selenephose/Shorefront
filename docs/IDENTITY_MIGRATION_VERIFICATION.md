# Shorefront identity migration — verification

Date: 2026-10-02. Baseline: `603398fa4cc3360ee3ff53ad89c0437292a5b1c8`.
Branch: `feat/shorefront-identity`. Last implementation commit at verification:
`e20d6d9`; documentation commits may follow it.

## Result

The source identity migration is implemented and verified locally. Public product
labels, package/module names, canonical settings, current docs and fresh-install
deployment names use Shorefront. Existing versioned contracts, metric names,
historical evidence and explicit configuration aliases are intentionally retained.

The GitHub repository metadata was renamed to `am-selenephos/shorefront` and the
incorrect archived/moved description corrected. At this report's creation, source
commits have **not** been pushed, merged or deployed. Main remained at the baseline.

## Fresh checks

| Check | Result |
| --- | --- |
| Original API baseline | 106 passed |
| Final API suite | **145 passed**, 4 existing dependency deprecation warnings |
| API suite with dummy inherited PostgreSQL URL, static path and weather feed | **145 passed**; isolated temporary SQLite selected before application import |
| Browser configuration inheritance regression | **1 passed**; dummy external database/feed settings overridden without connection |
| Full Chromium browser suite | **10 passed**, including a run with dummy inherited database/schema/public/static/feed settings |
| TypeScript check | Passed |
| Vite production build | Passed; pre-existing large-map chunk warning retained |
| Shell syntax | Passed for boot, prepare, bundle, backup and restore scripts |
| Compose/configuration/boot-preflight/backup-boundary tests | 16 cases included in the passing API suite; no containers started |
| Bundle construction and contents | Shorefront archive root and Python package; no .env, .venv, bytecode caches, database files or old package path |
| Git whitespace checks | Passed |
| Tracked artifact exclusions | No tracked .env, database, key, .venv, node_modules or execution-workspace paths |
| Historical README preservation | Byte-identical to baseline |

Baseline README SHA-256 and archived copy both:
`99cebaff102dde9f6cca8477bee1cd1cd9e7e6ff431dea4fb38e91bf9f63a350`.

The captured baseline synthetic evidence digest remains:
`661f963051076354821730959278fc84f719f73c1c2da115b761efaf3ea879d2`.
The regression suite also verifies old snapshot fields/providers/events and the
original restored recovery fingerprint, not just whether current code serializes.

Dependencies were installed fresh in this clone: `uv sync --frozen --extra dev`
and `npm ci --ignore-scripts`. Runtime: Python 3.14.7, Node 24.19.0; Compose CLI
5.5.0. No dependency directory was borrowed from another project.

Reproduction commands:

```sh
cd apps/api
uv run pytest -q
```

```sh
cd apps/web
npm run test:config
npm run typecheck
npm run build
npm run test:e2e
```

The pytest bootstrap now forces a dedicated temporary database before importing
the singleton app, clears inherited application configuration, and cleans up its
test directory afterward. The browser server explicitly selects its own temporary
SQLite URL and canonical test settings. Browser test directories are retained in
the system temporary folder for diagnostics; they contain synthetic test data only.

## Browser and visual evidence

Checks cover operator authentication, recovery receipt persistence, logout,
recorded-feed ingestion, vessel exception authority, the Shorefront product shell,
retired credential removal, initial loading identity and keyboard focus.

The actual app was captured at 1280×900, 768×1024 and 375×812 and visually inspected
for the identity change. Screenshots are local generated artifacts under
`apps/web/test-results/recovery-authority-Shorefr-e7ba6-ns-visible-across-viewports/`.
They are not committed customer screenshots or a redesigned UI. Existing layout,
colours and mobile navigation limitations remain; this is not whole-UI acceptance.

An initial browser run failed its first reset request while nine tests passed.
Investigation found an ignored generated `vite.config.js` could shadow the updated
TS configuration and use the old API-target environment key. Reintroducing that
stale file reproduced the failure. Explicit `--config vite.config.ts` in dev/build
fixed it; all ten tests then passed while the stale artifact was still present.
No retry or increased timeout was used to hide the failure.

The Vite map chunk remains approximately 1,013 kB minified / 276 kB gzip.
Development websocket teardown can emit EPIPE and runner colour-environment
warnings; all reported final assertions passed. These logs are not claimed pristine.

## Independent review and limits

A separate read-only reviewer inspected the baseline-to-implementation range and
pending README/browser/script changes. It found no Critical rename defects and one
Important test-isolation gap: inherited DATABASE_URL could escape temporary data
settings. The parent reproduced it with dummy settings, fixed both harnesses,
then reran all suites successfully. The reviewer did not independently execute the
suites or inspect final screenshots. This report and the single review-fix pass
were completed afterward; do not attribute them to a second review.

**Deferred minor:** BasicDeploy tests cover schema validation/preflight and syntax,
not a complete mocked boot through URL construction, authorization exports,
migration and server startup. Those paths were read, not executed. A full isolated
boot and production-shaped cutover are still required before release.

## Decisions and boundaries

- Use the owner-approved clean clone instead of another worktree. Cost: execution
  context lives in that separate clone, not the user's older release checkout.
- Require BasicDeploy's schema explicitly on both new installs and upgrades.
  Cost: existing deployment configuration must be updated before restarting.
- Pin the Vite TS entrypoint. Cost: launch scripts explicitly depend on that tracked path.
- Preserve old v1 IDs, metric names and historical evidence. Cost: technical legacy
  strings remain until separately versioned consumer migrations are approved.
- Keep authorization/reset/atomicity/replay product concerns outside this rename.
  Cost: this is not a commercial-readiness or operational-safety release.
- Do not claim PostgreSQL cutover, real-volume existence, backup restorability,
  rollback, TLS or BasicDeploy deployment proof. Cost: separate deployment gates remain.
- Keep palette/logo, tenant architecture, licensing and certification outside this
  change. Cost: the broader commercial/UI project remains unfinished.
- Separate parent-run tests and visuals from read-only review and remote metadata.
  Cost: no independent full-suite or live-deployment attestation is implied.
- This final report is parent-authored after review and checked against raw outputs;
  the reviewer did not approve unseen verification text.

No KRATIA source was edited. No new palette was applied. No real database was
migrated, restored or deleted. No secrets were rotated or published. A source-only
rename does not establish domain or trademark clearance.
