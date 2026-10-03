# Shorefront publication checkpoint — 3 October 2026

This records the source verification for the owner's request to commit, push and
deploy. It is not proof of a completed remote deployment or commercial readiness.

## Verified release content

- Standalone Shorefront identity and state-preserving legacy compatibility.
- Cream-first coastal interface, locally bundled geometric fonts and optional
  persistent inverse-contrast dark mode.
- Six focused workspaces, an isolated guided demonstration, and the optional full
  control tower. Role lenses affect presentation, not authorization.
- Freshness/shape guards, explicit connection errors and read-only stale states.
- Single-process command transactions, simulator rollback and cancellation-safe
  shutdown. One API runtime per database remains mandatory.
- Shared mutating demo controls default off; the isolated story still works.

## Fresh local verification

| Command | Result |
| --- | --- |
| `cd apps/api && uv run pytest -q` | 173 passed; 4 deprecation warnings |
| `cd apps/web && npm run typecheck` | Passed |
| `cd apps/web && npm run test:config` | 1 passed |
| `cd apps/web && npm run build` | Passed; lazy map chunk size warning remains |
| `cd apps/web && SHOREFRONT_E2E_BUILT=1 npm run test:e2e` | 31 Chromium tests passed |
| `cd apps/web && npm audit --omit=dev --audit-level=high` | 0 vulnerabilities reported |
| `git diff --check` | Passed |
| Deployment/backup shell syntax checks | Passed |
| BasicDeploy schema-only preflight with explicit `shorefront` schema | Passed; does not connect to a database |
| BasicDeploy bundle generation and archive inspection | Passed; built frontend, API and boot scripts only |

The bundle is local and ignored by Git:
`.artifacts/release-2026-10-03/shorefront-public-deploy.tgz`.
Tests use temporary SQLite databases; these results do not establish PostgreSQL
cutover, browser-engine parity, live restore or production failure recovery.

Release review identified an understated Pydantic minimum. Running the two legacy
evidence tests in an isolated Python 3.12 / Pydantic 2.11.10 environment reproduced
an added empty revision field and a changed historical evidence digest. The API
now requires Pydantic 2.12 or later, which introduced conditional field exclusion;
the locked version remains 2.13.5. This is a packaging compatibility correction,
not a rewrite of stored evidence. Both tests pass under the new minimum 2.12.0,
and the full locked suite passes again (173 tests). The font license text is retained, with trailing
whitespace removed from one line in each license.

## Deployment access and cutover gate

At this checkpoint, the historical BasicDeploy portfolio address returned HTTP
503. No BasicDeploy deployment tool or environment API key was available, and the
browser presented its sign-in page. No container, boot hook, database or secret was
changed. GitHub publication and live deployment are separate steps; the repository
workflow checks builds but does not publish this BasicDeploy runtime.

Before cutover, reconnect the owner's deployment access and confirm the existing
container and PostgreSQL schema. The historical schema name is a clue, not a safe
default. Preserve the selected database, stop the old application worker, keep
shared demo mutations disabled, and run one replacement worker. Follow
[the upgrade guide](RENAMING_AND_UPGRADING.md) for backup and rollback safeguards.
Verify the live UI, `/readyz`, WebSocket stream, capabilities, protected endpoints
and retained historical records before calling the deployment successful.

The wider commercial gates remain in [NEXT.md](NEXT.md). A successful source
publication must not be described as a final production SaaS release.
