# Shorefront source-authority hardening — 2026-10-08

## Scope and release provenance

- Repository: am-selenephos/shorefront
- Source commit deployed: ef0b8a7a1d7cbe0f24eae26bc537aec57d6e2009
- Canonical branch: feat/shorefront-v2-convergence
- Deployed images: shorefront-api:operational-ef0b8a7,
  shorefront-web:operational-ef0b8a7
- The images carry the exact same org.opencontainers.image.revision.
- Stable public origin: https://shorefront.animantum.com
- Customer data runtime: operational, not training.
- Product capability remains advisory_only=true and production_ready=false.

## Operational change

A berth/time proposal now includes explicit source-disagreement evidence
for the selected call, its vessel, original or candidate berth and port, and
related overlapping calls and their linked vessels/berths. These facts can be
disputed even if the geometric schedule checks are clear.

- Read-only Plan what-if displays the disputed record IDs and fields.
- Each new decision packet freezes this evidence inside every option.
- An alternative with relevant unresolved disagreements is ineligible.
- Approval rechecks unresolved source conflict state inside the database
  transaction, independently of the version-snapshot fingerprint.
- Disputes about unrelated vessels/ports do not block a different call.
- Human reconciliation is required before creating a newly eligible packet.
- Previously persisted packets without the new field remain readable.
- Source provenance, human review, audit receipts and existing supervisor
  approval authority remain intact.
- No automated vessel movement, crew dispatch, navigational clearance,
  weather/tide/AIS truth or predicted savings are claimed.

## Verification

- Fresh full API: 316 passed, 1 intentional PostgreSQL opt-in skip,
  4 existing dependency warnings.
- Focused decision intelligence and what-if tests: 8 passed.
- Full operational, training, and intelligence browser suites: PASS.
- TypeScript typecheck and production Vite build: PASS.
- Runtime configuration tests: PASS.
- Production npm audit: 0 vulnerabilities.
- Git diff integrity: PASS.
- Immutable source-labeled API and web images built successfully.
- Built-image HTTP/TLS Nginx delivery tests: 2/2 PASS.
- Stable external /readyz: HTTP 200, runtime_mode=operational.
- Stable external runtime capabilities: HTTP 200, advisory_only=true,
  production_ready=false.
- Stable anonymous decisions/readiness/reconciliation endpoints: HTTP 401.
- Public /metrics: HTTP 404.
- Public index.html SHA256 identical to deployed web-container index:
  a56aa54dab4186c37bc6cf972a62823c496149b4c1516f71e8c5ea7ea36298b1.
- Live Opera connected to the stable public showcase and rendered the
  MapLibre map, berth horizon, linked operating deck and read-only boundary.
- Protected internal decision workflows were verified against isolated test
  storage, not by seeding customer records into the live database.

## Data protection and cutover

- Predeploy archive:
  /home/nur/.local/share/shorefront/backups/shorefront-pre-source-authority-20261008T112715Z.dump
- Checksum sidecar verified and pg_restore could list the archive.
  An actual restore rehearsal of this particular archive was not performed.
- Previous private environment backup:
  /home/nur/.local/share/shorefront/operational.env.pre-source-authority-20261008T112715Z
- Only API and web were recreated, using no-deps and wait.
- PostgreSQL container ID remained:
  f8faa1582de507aad6344bc7f00222b3a229230e0e07acab952474a3609bb04d
- PostgreSQL start time remained: 2026-10-07T23:18:12.210791688Z
- No schema migration, volume deletion or customer-demo seeding occurred.
- The operational healthcheck passed with internal metrics accessible only
  within the service network and public metrics hidden.

## Outstanding commercial release gates

The source-authority rule is deliberately deterministic and bounded. A real
pilot still needs qualified source/data contracts, verification of stale
records, practical resource-to-call allocation, accepted harbor authority
and downstream stakeholder agreements, operational calibration against real
outcomes, independent security assurance, performance/retention qualification,
and encrypted offsite recovery with actual RTO/RPO evidence.

GitHub Actions availability must be checked separately: local Playwright
passes do not imply that GitHub's remote CI was executed.
