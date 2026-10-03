# Shorefront verification plan

Test new behavior before production implementation:

1. Comparison returns engine-consistent projected states and leaves live state
   and durable evidence unchanged.
2. Guided story computes disruption/recovery, marks synthetic approval, and leaves
   the live store unchanged across repeated requests.
3. Workspace navigation, reload/back, role lens, mobile overflow and headings.
4. Guided demo only performs read requests; exit restores operational workspace.
5. Failed initial state can retry; silent transport becomes visibly stale; inactive
   effects cannot reconnect or overwrite a newer state.
6. Existing recovery authority, adapter, palette and theme browser workflows remain
   covered through the optional full control tower plus new focused-workspace tests.
7. Fresh full API suite, typecheck, config tests, production build, Chromium dev
   and built-preview checks, followed by screenshot inspection.

No tests for unimplemented roadmap capabilities are claimed. No live integration,
cross-engine or commercial readiness is established by these local checks.

## Verified 2026-10-03

Latest follow-on: atomic-command changes now pass **173 API tests** and **31
built-app Chromium tests**. See [atomic-command verification](../../ATOMIC_COMMAND_VERIFICATION.md).
The table below preserves the earlier UI milestone's counts.

| Check | Fresh result |
| --- | --- |
| `uv run pytest -q` in `apps/api` | 156 passed, four deprecation warnings |
| `npm run typecheck` in `apps/web` | Passed |
| `npm run test:config` | 1 passed |
| `npm run build` | Passed; lazy map chunk size warning remains |
| `npm run test:e2e` | 31 passed, Chromium development server |
| `SHOREFRONT_E2E_BUILT=1 npm run test:e2e` | 31 passed, Chromium built preview |
| `git diff --check` | Passed |

Evidence is preserved locally under
`.artifacts/decision-workspaces-2026-10-03/` (git-ignored), including full final
API/build/browser logs and built-browser screenshots. These are not committed
release artifacts. See [the milestone verification report](../../DECISION_WORKSPACE_VERIFICATION.md).

## Red/green and review record

- Comparison/story API tests first failed with missing-endpoint 404s, then passed.
- Workspace, navigation, demo, mobile and error-state requirements were exercised
  before implementing their UI. Hardening failures caught default button styling,
  a below-fold mobile queue and false empty-success recovery output.
- Shared-demo boundary tests caught unguarded mutation endpoints before the
  canonical opt-in and protected-runtime UI were added.
- Independent review found comparison invalidation, offline logout and nested
  transport validation gaps. Browser regression tests reproduced them before fixes.
- Five new engine revision tests failed before the additive revision existed and
  now pass. Full API regression then caught changed legacy serialization; omitting
  absent revision values restored both original evidence-digest tests.
- A malformed-stream reconnect test caught mutation controls being re-enabled
  without valid data. The guard now remains closed while a data error is active.
- Screenshot capture now completes finite theme transitions before recording
  contrast; the earlier immediate-transition image was not a settled-state defect.

The suite uses disposable SQLite databases, test-only identities and deliberately
unavailable/empty live-feed endpoints. No real operational reset, paid API, live
port integration, production database or external delivery was used.
