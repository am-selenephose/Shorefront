# Shorefront operational product design

## Authority and intent

The user approved the isolated-customer architecture and explicitly requested continuous
implementation without routine design-review pauses. This specification records those
decisions; it does not claim the full programme is delivered. Work in the existing clean
`feat/shorefront-identity` checkout. No production data, credentials or deployments are
changed as part of local implementation.

Shorefront is a human-operated maritime coordination and evidence product, not vessel
control, a TOS replacement, a legal authority or a source of invented financial results.
Preserve the approved cream/teal palette, local Space Grotesk/Space Mono and dark mode.

## Programme and dependency order

1. Operational runtime, accounts, durable records, customer ownership and browser onboarding.
2. Versioned operational graph, valid-time/knowledge-time history and accountable attention.
3. Commitments, handoffs with recipient acknowledgement, obligations and partner projections.
4. Evidence-bound decisions, trust envelopes, historical comparisons and observed outcomes.
5. Validated external adapters, standards contracts, distributed reconciliation and hardening.
6. Deployment, backup/restore rehearsal, customer acceptance and verified commercial workflows.

Each stage remains separately testable. Licensed feeds, external identity-provider setup,
customer contractual interpretation and deployment credentials cannot be manufactured.
Claims submission and money movement remain outside autonomous execution.

## First integrated product: operational workspace

### Runtime boundary

`SHOREFRONT_RUNTIME_MODE=operational` is the default. `training` explicitly selects the
existing simulator. The operational app has independent route registration and versioned
`sf_*` tables; it never loads legacy harbor snapshots or simulator fixtures. Legacy tables
and evidence bytes remain unchanged. Training and operational deployments must use separate
database credentials/origins. Selecting a mode is not a data migration.

Operational startup requires a stable `SHOREFRONT_INSTALLATION_ID` and exact browser
`SHOREFRONT_ORIGIN`. An existing database owner mismatch fails closed. Production origins
require HTTPS; HTTP is only allowed for loopback development. One database belongs to one
installation. There is no shared-SaaS tenancy claim.

### Accounts and authority

Expiring, single-use administrator bootstrap requires an out-of-band secret. Passwords use
salted scrypt, not a fast digest. Opaque session cookies are HttpOnly, SameSite=Strict, Secure
outside loopback, expire after eight hours and are stored only as digests. Mutations check
both exact Origin and session-bound CSRF. Login attempts are rate-limited persistently.
Sign-out revokes the server session. Administrators issue expiring one-time invitations;
tokens appear once, are never stored in plaintext and require explicit safe sharing.
No email is sent without a configured, authorized service.

Roles: administrator manages membership and configuration; operator manages operational
records; supervisor additionally approves decisions; viewer reads. Administrative authority
does not automatically grant decision approval. Partner access is disabled until the
resource/field projection and revocation tests pass. Revoked accounts lose sessions.
Every read, history, export and stream endpoint checks session authority; only minimal
health/capabilities and sign-in/bootstrap endpoints are public.

### Durable facts and commands

Typed port, berth, vessel, call, resource, incident and task records are server-validated.
Each accepted version stores actor, source, effective time and server knowledge time.
No background process manufactures movements, weather, service completion or source health.
Missing observations remain absent. All references resolve within the installation.

Commands supply idempotency keys and expected revisions. Same actor/key/payload returns
the original committed response; different intent conflicts. Stale revisions return 409.
Record version, audit event and command result commit in one transaction. SQLite obtains a
database write reservation; PostgreSQL uses transaction-scoped advisory serialization.
There is no mutable in-memory authoritative harbor state and no process-local lock claim.

Append-only revisions permit knowledge-time and effective-time reads. Corrections preserve
prior versions. Audit entries form a canonical SHA-256 chain: verification detects ordinary
modification but is explicitly not a signature or protection against an administrator
rewriting the entire database. Exports contain the original records and verification result.

### Frontend

The boot entry chooses the server-declared runtime; failures show retry, never fallback to
a demo. Operational UI includes onboarding/sign-in, Pulse, Records, history/evidence and
Team. Typed forms, meaningful empty states, errors preserving input, pending state and
server-authoritative updates are required. Credentials remain out of local/session storage.
Expired/revoked authority clears displayed customer data. Offline data is visibly stale and
writes are disabled; sign-out can hide local data but must not claim server revocation if
the network request fails. Polling or streams must be bounded and cleaned up on logout.

### Acceptance and release gates

Empty installation -> bootstrap owner -> invite operator -> create port/berth/vessel/call ->
record incident -> assign task -> update task -> restart -> retain records and audit history.
Prove denied anonymous access, CSRF/origin rejection, viewer write denial, revocation,
one-time invitation use, idempotency across restart, stale revision rejection, rollback,
historical reconstruction, owner mismatch and isolation from synthetic history.
Browser tests exercise the real API at desktop/mobile and both themes.

Production release also requires PostgreSQL verification, TLS, backup/restore rehearsal,
monitoring, bounded storage/requests, successful deployment and customer-specific operational
validation. A locally passing suite alone never changes `production_ready` to true.
