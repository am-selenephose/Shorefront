# Shorefront operational decision intelligence release — 2026-10-08

## Exact artifact and operational scope

- Repository: am-selenephos/shorefront; canonical branch: feat/shorefront-v2-convergence
- Deployed application source: aa7f9f0c1e0911b964f53b3d1aeed13d796181d6
- Feature implementation commit: 8a2b2705f1e4ead38e6ab4397a7eec83548da0df
- Deployed API image: shorefront-api:operational-aa7f9f0
- Deployed web image: shorefront-web:operational-aa7f9f0
- Both built images have the same exact application source revision label.
- Public host: https://shorefront.animantum.com
- Runtime: dedicated operational, intentionally not a seeded training workspace.
- Only operational API and web containers were recreated with --no-deps --wait.
- PostgreSQL container ID f8faa1582de507aad6344bc7f00222b3a229230e0e07acab952474a3609bb04d remained unchanged and healthy. No database migration or volume reset was performed.

## Working operator journey

1. In Plan, an authenticated operator compares a recorded call to a berth and time proposal. The read-only result includes introduced or cleared conflicts, related calls, open accountable work, unavailable port-wide resources and missing evidence.
2. An explicit Save exact scenario action freezes the proposed berth and UTC times in an auditable decision packet. It does not mutate the recorded call.
3. The operator can open the exact packet in Recovery. Each alternative carries source-aware reasons and an evidence-oriented review ordering, rather than a predicted traffic outcome or automatic decision.
4. Only a supervisor can approve an eligible option with an explanation, and a stale or tampered input snapshot prevents application. Approval changes the recorded call schedule and retains evidence.
5. Actual outcomes require separate human recording. Unregistered and cross-port berth proposals are rejected.

## Verification record

- Full API tests: **314 passed**, one intentionally skipped dedicated-PostgreSQL opt-in, existing dependency warnings.
- Full operational browser suite on the integrated Quay/Decision Intelligence source: **38/38 passed**.
- Training/demo browser suite: **31/31 passed**.
- Separate intelligence browser suite: **3/3 passed**, including a real browser flow from exact scenario to recovery, independent supervisor login, approval, verified new call record and valid audit ledger, all on disposable test storage.
- TypeScript typecheck, production Vite build, runtime config test and production dependency audit passed; npm audit reported 0 vulnerabilities.
- Actual built web image passed HTTP and TLS Nginx cache/header tests: **2/2 passed**.
- After cutover, API/web and PostgreSQL healthy. Public root, readiness and capabilities returned HTTP 200; unauthenticated decisions and readiness API returned 401.
- Public index.html SHA256: 68e353e1a39faa29fe467e78bc641a94bad0da553b6565e3a667c0770a8ca08a, identical to the running web image.
- Operational healthcheck passed: all services running, internal metrics present, public metrics endpoint hidden. Existing user health/backup timers remain enabled; user linger is enabled.

## Recovery and continuity

- Fresh predeploy PostgreSQL dump: /home/nur/.local/share/shorefront/backups/shorefront-pre-decision-20261008T110706Z.dump
- Backup SHA256 sidecar verified. Backup files mode 0600; directory mode 0700; owned by nur.
- Previous private deployment environment copied to /home/nur/.local/share/shorefront/operational.env.pre-aa7f9f0 (0600).
- Previous images tagged independently as shorefront-api:rollback-pre-aa7f9f0 and shorefront-web:rollback-pre-aa7f9f0.
- Private operational environment updated atomically after successful health checks to image tag operational-aa7f9f0 (0600), retaining existing installation identity and credentials.
- The fresh backup was checksum-verified but **not restored in a rehearsal** during this particular cutover. It is local, not an offsite encrypted recovery guarantee.
- No authenticated test or simulated port records were written to the existing operational customer database during release checks.

## Explicit limitations

This is deterministic recorded-data **decision support**, not live vessel control or a navigational-safety approval. No licensed AIS, PCS/TOS, weather/tide, pilot, under-keel clearance, resource-to-call allocation, cross-organization agreement or calibrated delay forecast is established by this increment. No paid port pilot, independent security review, externally validated safety case, production load qualification, SAML/OIDC, or encrypted/offsite RTO/RPO-assured recovery has been completed.

The public capabilities endpoint intentionally continues to state production_ready=false and advisory_only=true. Do not market this release as commercially certified or as predictive savings.
