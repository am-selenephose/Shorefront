# Shorefront V2 resource and observed-outcome intelligence release — 2026-10-08

## Exact operational deployment

- Repository: am-selenephos/shorefront
- Canonical branch: feat/shorefront-v2-convergence
- Application source commit: 8b86401968f28d0e6adc4ba6b4d2d139fe81bfab
- Images: shorefront-api:operational-8b86401 and shorefront-web:operational-8b86401, each built from this commit with the revision label.
- Stable HTTPS origin: https://shorefront.animantum.com
- API/web cutover used operational Compose with --no-deps --wait, preserving all PostgreSQL records.
- PostgreSQL container: f8faa1582de507aad6344bc7f00222b3a229230e0e07acab952474a3609bb04d, unchanged before/after including StartedAt 2026-10-07T23:18:12.210791688Z.
- No database schema change, database migration, simulation seed, customer data import, or credential rotation performed for this release.

## New connected product capability

1. A resource_assignment is a versioned, evidence-attributed, time-bounded link between an existing port call and an existing specific resource (pilot, tug, crew or equipment).
2. Transactional confirmation enforces same port, finite ordered times, immutable call/resource identity, documented human confirmation, resource availability, and no overlapping confirmed assignment. A released allocation cannot be reopened.
3. A scoped integration bearer may ingest proposed allocations, but cannot claim to be the human confirming/releasing them. Source revocation and idempotency still apply.
4. The Plan screen contains the exact allocation register; Readiness checks explicitly confirmed assignments per call; What-If and Recovery show assigned resources, unavailable/overbooked resources, missing evidence, and required reconfirmation after a schedule change.
5. The measured-outcome API at /api/v1/decision-intelligence/outcomes and Recovery dashboard report approved-decision coverage, missing observations, and named-source arrival/departure/occupancy deviations without calculating causal savings.
6. The Connections page surfaces successful ingestion receipts and warns if no record ingestion occurred within sixty minutes; receipt age is explicitly not claimed to be true provider observation age.

## Verified regression evidence

- API pytest: 320 passed, 1 intentional optional PostgreSQL skip, 4 existing dependency warnings.
- Separate disposable PostgreSQL integration: 1/1 passed, including schema ownership and backup/restore checks.
- Operational browser: 38/38 passed.
- Training/browser simulator: 31/31 passed.
- Intelligence browser suite: 4/4 passed, including new mobile resource allocation and measurement coverage acceptance.
- TypeScript typecheck, Vite production build, runtime config 1/1, production npm audit 0 vulnerabilities, and git diff integrity passed.
- Built immutable web-image HTTP/TLS delivery regression: 2/2 passed.
- Public root, /readyz, runtime capabilities: HTTP 200.
- Unauthenticated /api/v1/decisions, /api/v1/decision-intelligence/outcomes, /api/v1/readiness: HTTP 401.
- Public root SHA256 matches released Nginx image index.html: 7e2633e474709346b4065238ff484f116e155943a6c58d12168dcc4d178c43c3.
- Operational health script: health=ok; runtime=operational; postgres/api/web running; public metrics hidden.
- Production runtime capabilities: advisory_only=true, production_ready=false.

## Backup, rollback, and continuity

- New pre-cutover PostgreSQL custom dump: /home/nur/.local/share/shorefront/backups/shorefront-pre-resource-intelligence-20261008T123500Z.dump
- Matching SHA256 sidecar passed verification. Both are owned by nur, permissions 0600, in the protected backup directory.
- Previous operational environment preserved: /home/nur/.local/share/shorefront/operational.env.pre-8b86401, mode 0600.
- Previous independently deployed images tagged shorefront-api:rollback-pre-8b86401 and shorefront-web:rollback-pre-8b86401.
- Live private deployment environment atomically updated to SHOREFRONT_IMAGE_TAG=operational-8b86401 and validated against Compose, mode 0600.
- This cutover did not execute a separate restore of its newly created dump. A disposable PostgreSQL integration test exercised a separate backup/restore.
- Existing customer data volume was not recreated.

## Boundaries and next external prerequisite

A real vendor/port feed has NOT been activated in this release. No AIS/PCS/TOS/pilot provider credential, signed contract, accepted provider schema, independent observation freshness, actual dispatcher acknowledgement, or live operations acceptance was supplied. The generic authenticated normalized source-ingestion path is ready for supervised onboarding once those inputs are available.

The measurement system reports descriptive deviations, not a calibrated causal estimator, weather/navigational clearance, automatic equipment dispatch, or an assured ROI. Real operational provider integration and port pilot validation remain required for enterprise production claims.
