# Shorefront optional NOAA context — verified release 2026-10-09

Canonical repository: am-selenephos/shorefront
Canonical branch: feat/shorefront-v2-convergence
Deployed source/image revision: 859fa69e01622f4d651be76cfdc485a31fca516e
Stable origin: https://shorefront.animantum.com
Images: shorefront-api:operational-859fa69, shorefront-web:operational-859fa69
Deployment: Compose --no-deps --wait of API followed by web, without DB recreation.

## What changed
- Optional read-only NOAA CO-OPS water-level context in Plan workspace,
  selected by an explicit operator-recorded seven-digit station ID.
- Observation source, quality, station identity, datum, units, timestamp and
  freshness/outage states are disclosed. Invalid and stale responses fail closed.
- Operational Compose passes SHOREFRONT_NOAA_ENABLED to the API. It is OFF
  unless the installation owner explicitly opts in. Production remains OFF.
- Manual workspace Refresh handles out-of-band record ingestion.
- No station assignment is pre-populated or independently geographically
  verified. This is not navigational clearance, vessel movement authorization,
  a tide-adjusted draft calculation or paid AIS/TOS/PCS integration.

## Evidence
- Full backend: 330 passed, 1 optional PostgreSQL skip; separately tested
  disposable PostgreSQL 1/1 including backup/restore.
- The recorded weather training-fixture test was stabilized against measured
  elapsed wall time. Full API regression passed.
- Chromium operational browser: 38/38; training: 31/31; intelligence: 5/5.
- TypeScript, Vite build, runtime config, npm production dependency audit pass;
  0 audited production vulnerabilities.
- Pinned web image HTTP/TLS delivery: 2/2 passed.
- Public readiness and capabilities HTTP 200; advisory_only true,
  production_ready false; external NOAA unauthenticated access HTTP 401.
- Public HTML sha256: 12aacd5ed9baf384cbadbdfb73231ad962e3e521357202149c773855323fa1d2
  matches deployed Nginx image exactly.
- Public Chromium visual checks: 14/14 showcase workspaces across desktop
  1440px and mobile 390px, zero page-width overflow and uncaught JS errors.
- Public light-to-dark theme switching passed both viewports, Pulse/Plan/
  Coordination remained page-contained. Opera connector was unavailable.
- Postrelease operational health:
  health=ok runtime=operational services=postgres,api,web public_metrics=hidden

## Persistence and rollback
Pre-release PostgreSQL container and post-release container both:
f8faa1582de507aad6344bc7f00222b3a229230e0e07acab952474a3609bb04d
StartedAt remains 2026-10-07T23:18:12.210791688Z, healthy.
Precutover backup: /home/nur/.local/share/shorefront/backups/shorefront-pre-noaa-20261009T000821Z.dump
SHA256 sidecar passed; both files chmod 0600 and owned by nur.
Environment snapshot: /home/nur/.local/share/shorefront/operational.env.pre-859fa69
Rollback image tags: shorefront-api:rollback-pre-859fa69,
shorefront-web:rollback-pre-859fa69.
No customer database migration, reset, seed, credential rotation or volume
recreation occurred during this release.

## Commercial limits
An actual design partner and authorized external operational source are still
needed, along with provider schema/clock/quality acceptance, operational
decision authority, incident handling, measured business outcomes,
independent security qualification and operator user acceptance. NOAA data
alone cannot substantiate autonomous port scheduling or forecasted savings.
