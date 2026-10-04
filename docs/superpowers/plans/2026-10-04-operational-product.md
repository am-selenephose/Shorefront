# Shorefront Operational Product Implementation Plan

> **Execution record:** The user requested continuous execution; routine approval handoffs were waived. Initial work was inline. Later collaboration instructions authorized bounded parallel help, interrupted by service usage limits; final review was local. See `docs/OPERATIONAL_PRODUCT_STATUS.md` for current evidence and remaining release gates. This plan covers the first integrated operational workspace, not the entire infrastructure programme.

**Goal:** Deliver an authenticated, durable customer workspace independent of training fixtures.

**Architecture:** Separate operational FastAPI app over versioned relational tables. React selects the actual server runtime. Authoritative commands are database transactions, not simulator mutations.

**Tech Stack:** Existing FastAPI, Pydantic 2.12+, SQLAlchemy 2, SQLite/PostgreSQL, React 19, TypeScript, Playwright. Standard-library scrypt for password hashing.

**Spec:** `docs/superpowers/specs/2026-10-04-operational-product-design.md`

## Global Constraints

- Shorefront branding, existing coastal tokens, local Space Grotesk/Space Mono, remembered dark mode.
- No synthetic observations or legacy data rewriting in operational mode.
- One immutable installation owner per database; no shared-SaaS isolation claim.
- All operational reads/writes require session authority; CSRF and Origin required for cookie mutations.
- Administrative authority does not imply decision approval.
- Commands atomically persist record, audit and idempotent result; unknown inputs remain unknown.
- No deployment, spending, licensed-feed access or legal/financial effects fabricated.

## Review Focus

- Concurrent/retried commands must not overwrite or duplicate a committed result.
- Expired/revoked sessions must clear customer data and deny future reads.
- Future-dated corrections must not contaminate an earlier effective/knowledge-time view.
- Missing setup, malformed imports and server errors must preserve user input without demo fallback.
- Restoring a database belonging to a different customer must fail, not reassign ownership.

### Task 1: Isolated operational storage and typed records

**Files:** Create `apps/api/src/shorefront_api/product_models.py`, `product_store.py`; test `apps/api/tests/test_product.py`.

**Interfaces:** `ProductStore(database_url, installation_id)`, `initialize()`, `transaction()`; typed `RecordCommand` with `record_id`, `expected_revision`, `valid_at`, `source`, `payload`. `write_record(connection, actor, kind, command, idempotency_key)` returns persisted record. `snapshot(connection, known_at=None, valid_at=None)` returns original versioned records.

- [x] Write tests proving fresh empty state, two-clock history, stale revision, atomic idempotency, reference validation and wrong-owner denial.
- [x] Run `uv run --frozen pytest tests/test_product.py -q`; observe missing feature failures.
- [x] Implement namespaced tables and transaction serialization, strict typed payloads and history/audit chain.
- [x] Run focused tests and the full API suite; include in the integrated verified checkpoint.

### Task 2: Account lifecycle and operational routes

**Files:** Create `product_auth.py`, `product_api.py`; modify `main.py`, `tests/conftest.py`; extend `test_product.py`.

**Interfaces:** `create_product_app(database_url=None, installation_id=None, origin=None, bootstrap_token=None)`; `/api/v1/auth/{bootstrap,login,me,logout,invitations,accept}`, `/api/v1/workspace`, `/api/v1/records/{kind}`, `/api/v1/history`, `/api/v1/evidence`, `/api/v1/team`.

- [x] Test bootstrap, login, CSRF/origin, viewer denial, invitation expiry/reuse, revocation, persistence and protected reads against real TestClient/temporary DB.
- [x] Run focused tests; observe expected missing-route/authority failures.
- [x] Implement salted passwords, digested sessions/invitations, rate limits, immutable ownership, bounded inputs and transactional authorization.
- [x] Select operational mode by default, explicitly opt legacy tests into training; run all API tests.

### Task 3: Browser product workflow

**Files:** Create `apps/web/src/ProductApp.tsx`, `product.css`, `productClient.ts`, `apps/web/e2e-product/product.spec.ts`, `playwright.product.config.ts`; modify `main.tsx`, existing Playwright config and package scripts.

**Interfaces:** Capabilities returns `runtime_mode`; product client sends exact Origin automatically and CSRF header from `/auth/me`, uses same-origin cookies, aborts requests after 10 seconds.

- [x] Add real browser onboarding/records/invitation/session/theme/mobile tests and watch fail before UI implementation.
- [x] Build operational shell, typed record forms, Pulse tasks, history/export and team administration using existing tokens.
- [x] Run typecheck, config tests, build, original browser suite and product browser suite; inspect screenshots.

### Task 4: Coordination and evidence extensions

**Files:** Extend `product_models.py`, `product_store.py`, `product_api.py`, frontend forms and tests; add focused domain modules as needed.

**Interfaces:** Typed commitment/handoff/obligation records, explicit authorized transitions, recipient acknowledgement proof, derived relationship graph, immutable decision packets and observed-outcome records.

- [x] Add failing transition/recipient/stale evidence/history tests for each independent capability before implementation.
- [x] Implement only truthful state transitions and derived views; no fake external acknowledgement or modeled cash receipts.
- [x] Verify API and browser journeys end-to-end and update programme ledger with actual proof/gaps.

### Task 5: Release preparation

**Files:** Deployment configuration, README, `docs/OPERATIONAL_PRODUCT_STATUS.md`, tests as needed.

- [x] Document safe empty installation, explicit training, account recovery, backup and migration ownership.
- [x] Verify startup defaults and schemas against isolated local storage; run complete suites.
- [x] Review full diff in a separate self-review pass; fix with regression tests. Independent review remains a release gate.
- [ ] Commit/push the verified checkpoint; deploy only with an explicitly confirmed operational target and access. Record unpassed gates accurately.
