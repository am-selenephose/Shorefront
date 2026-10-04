# Shorefront Actionable Workspaces Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation,
> with bounded parallel backend/review work. The user's continuous-execution direction
> waives routine design/plan pauses. Preserve the existing feature checkout.

**Goal:** Make real operational records actionable from dedicated workspaces.

**Architecture:** Existing versioned record API remains authoritative. A server-derived
coordination projection supplies actions; focused React workspaces consume it and submit
normal revision-checked commands. Contextual editors reuse the current record forms.

**Tech Stack:** Existing FastAPI, SQLAlchemy, React, TypeScript and Playwright; no new service.

**Spec:** `docs/superpowers/specs/2026-10-04-actionable-workspaces-design.md`

## Global Constraints

- Preserve `brand.md`, cream-first theme and remembered night mode.
- No customer data is inserted into the supplied tunnel.
- Mutation authority, revision checks, idempotency, Origin, CSRF and audit atomicity remain server enforced.
- Closed workflow records stay sealed. Original terms and timestamp precision survive transition forms.
- No fake maps, resource geometry or savings. No deployment in this increment.

## Review Focus

- Nonzero seconds or non-UTC due dates must survive recipient acknowledgement (Task 1/2).
- Revoked/viewer recipients and stale revisions must not gain write authority (Task 1/2).
- Polling or failed refresh must not erase an open form or repeat a committed mutation (Task 2/3).
- Multiple pending replay requests must not display an older response under newer clocks (Task 4).
- An empty installation, small viewport or populated call with many threads must retain a clear next action (Task 3).

### Task 1: Server-derived coordination actions

**Files:** `product_coordination.py`, `product_api.py`, `tests/test_product_workflows.py`
under `apps/api/src/shorefront_api` and `apps/api/tests` respectively.
**Interfaces:** `GET /api/v1/coordination` → `{items:[{record, creator_id, actions:[{status,label,requires_proof,requires_review}]}], read_at}`.
Consumes current snapshot, first-version creator and authenticated user. Normal record
writes remain the only mutation path; projection shares authorization rules.

- [ ] Tests: unauthenticated 401; viewer actions empty; originator can send but not acknowledge;
  recipient can acknowledge only sent records; terminal has no actions; obligation review/proof requirements.
- [ ] Run new tests and observe missing endpoint failures.
- [ ] Implement projection without changing existing state semantics; retain full raw terms.
- [ ] Run API suite; record results and any discovered integrity correction separately.

### Task 2: Coordination workspace

**Files:** create `apps/web/src/ProductCoordination.tsx`, modify `ProductApp.tsx`,
`product.css`, add `apps/web/e2e-product/workflows.spec.ts`.
**Interfaces:** component takes `facts`, `team`, `user`, `writable`, `onRefresh`, `onCreate`.
Consumes Task 1 projection; submits `/records/{kind}` with expected revision, source and
stable idempotency key; copies untouched payload values exactly.

- [ ] Browser test named-party handoff with second-precision offset due date, commitment
  completion, sealed action state and offline input preservation. Observe missing UI failure.
- [ ] Build desk, filters, source/proof transitions and creation entry points.
- [ ] Run workflow suite and regression suite; inspect desktop/mobile both themes.

### Task 3: Contextual operations and first-use path

**Files:** `ProductOperations.tsx`, `ProductRecords.tsx`, `ProductApp.tsx`, `product.css`,
`e2e-product/workflows.spec.ts`.
**Interfaces:** shared editor accepts optional initial payload and fixed kind; root manages
editor identity independently of polling. Operations receive explicit create/edit callbacks.

- [ ] Test empty setup CTA, create linked incident/task from a call, edit from Exceptions,
  preserve open inputs while polling, viewer/offline disabled controls, visible overflow count.
- [ ] Run targeted tests, observe missing action failures.
- [ ] Add onboarding actions, linked thread actions, full queue navigation and schedule conflicts.
- [ ] Run all operational browser tests, TypeScript/build and training regressions.

### Task 4: Inspectable historical facts

**Files:** create `ProductEvidence.tsx`, replace inline Evidence in `ProductApp.tsx`,
extend `e2e-product/workflows.spec.ts`.
**Interfaces:** component consumes `facts`/`team`, existing history/workspace/evidence routes.
Reconstruction retains selected clock labels, full fact payload/source/actor and current
comparison, and guards request generations.

- [ ] Test a corrected fact displays the old payload/source at earlier knowledge time,
  current difference, read-only state and latest-response-wins behavior.
- [ ] Observe failure, implement view, run new and full relevant suites.
- [ ] Fresh code review, fixes with regressions, update delivery ledger and commit verified changes.
