# Operator readability hardening (2026-10-09)

This increment responds to the measured finding that critical Shorefront UI
uses excessive 10-13px typography, including berth labels, source indicators,
control labels, planning dates, call-row descriptions and error explanations.

## Changed

- Explicit CSS font and font-size declarations smaller than 14px were
  promoted to 14px in apps/web/src/product.css,
  apps/web/src/styles.css, and apps/web/src/ProductEvidence.css.
- Scope: 394 declarations in the operational stylesheet, 208 in shared
  simulator/showcase styling, 11 in evidence-specific styling; 613 total.
- Headline sizes, data contents, API behavior, source/time provenance,
  color identity, accessible theme switching, read-only/live separation, and
  existing Quay/map fullscreen functionality were kept intact.
- A durable unit guard prevents future sub-14px explicit text rules in these
  files (npm run test:config), and browser checks assert computed operator
  sizes, Quay fullscreen, theme switching and no page-width overflow at
  1440px, 390px and 320px (npm run test:readability).

## Verification (isolated disposable runtime, not production data)

- TypeScript typecheck and Vite production build passed.
- Full backend regression: 330 passed; one intentional PostgreSQL opt-in skip.
- Full operational Chromium regression: 41 passed.
- Dedicated Chromium 3/3 and Firefox 3/3 operator readability checks.
- WebKit locally blocked by missing host runtime libraries before browser
  launch. This is neither a browser pass nor a proven product failure.
  GitHub CI's existing matrix explicitly installs WebKit dependencies on
  Ubuntu. Confirm a fresh WebKit run before promising full cross-browser
  acceptance.
- The isolated initial full-suite run on ports 5188/8188 had 10 expected
  403s from existing tests that hardcode origin 5176; this was resolved by
  rerunning the full suite under the canonical product test config at
  5176/8151, without weakening server origin checks. 41/41 passed.
- No customer records were imported, changed or fabricated.

## Commercial product quality gates still open

The 10/10 target requires independent evidence, not changed score labels:

- Engineering: load/capacity tests with independently authorized real
  data volumes, external security and accessibility review, verified
  offsite encrypted restore, measurable incident RTO/RPO, Firefox/WebKit
  full workflow certification, and signed-off release/runbook operations.
- Visual: user-tested responsive hierarchy, adjustable column density,
  verified keyboard workflows, documented WCAG contrast and focus checks,
  and a Quay interaction usability benchmark on real planning use cases.
- Market: a named paying buyer/design partner, authorized external
  port/TOS/PCS/AIS data contracts and freshness acceptance, observed call-to-
  decision workflow completion, documented customer ROI without invented
  causal savings, and an agreed commercial SLA/support boundary.

The verified score is not automatically 10/10 after these changes. The app
still reports production_ready=false by design, and only real commercial
acceptance can resolve the final market gates.
