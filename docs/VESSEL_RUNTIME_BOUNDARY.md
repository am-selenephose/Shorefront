# Shorefront <-> Vessel Runtime Boundary v1

> The product name is Shorefront. The `portflow.*.v1` identifiers below are
> deliberately frozen published contracts; senders need not rename envelopes.
> Runtime configuration uses `SHOREFRONT_*`, with legacy aliases and explicit
> precedence documented in [Renaming and upgrading](RENAMING_AND_UPGRADING.md).

## Purpose

Shorefront is the port-side coordination and recovery-control plane.
A future vessel-side intelligence runtime is a separate repository and a separate operational authority domain.

The two systems exchange normalized operational messages, but they do not share code ownership or permission authority.

## Ownership split

Vessel runtime owns raw navigation and machinery sensors, onboard perception, equipment health, local voyage/energy/navigation reasoning, bridge and engine-room HMIs, future actuator integrations, vessel-local safety interlocks, and high-rate telemetry retention.

Shorefront owns port-call timelines, berth/resource coordination, service dependencies, port-side incidents, recovery proposals, human approval receipts, evidence snapshots, and the port-side integration event ledger.

## Hard safety boundary

Shorefront coordination responses are advisory only.

Every coordination snapshot carries:

- advisory_only = true
- requires_human_approval = true
- actuation_allowed = false

Shorefront does not directly command helm, propulsion, thrusters, steering gear, autopilot, DP, machinery, or onboard safety systems.

A vessel-runtime integration credential is not an operator credential and cannot approve a Shorefront recovery proposal.

## Authentication plane

Human operator credentials use SHOREFRONT_APPROVERS_JSON.
Machine integration credentials use SHOREFRONT_INTEGRATIONS_JSON.

Each integration record contains token_sha256, integration_id, display_name, and vessel_ids.
The vessel_ids allowlist scopes the integration to explicitly authorized vessels.

## Inbound event contract

Contract id: portflow.vessel-event.v1

Endpoint:

    POST /api/v1/integration/vessel-events

The envelope contains event_id, occurred_at, vessel_id, optional port_call_id, event_type, sequence, source_system, normalized payload, and optional evidence_refs.

Supported v1 event types:

- position
- eta
- readiness
- constraint
- connectivity

This contract accepts normalized operational events, not raw high-rate sensor streams.

Payload size is capped at 64 KiB.
event_id is the idempotency key.

Repeating the same event id with identical content under the same integration returns duplicate=true and the original acceptance time.
Reusing the same event id with different content or another integration returns HTTP 409.

The sequence field is source-local ordering metadata. Shorefront stores it but does not assume globally ordered delivery.

## Durable event ledger

Accepted events are stored immutably in schema v3 table vessel_runtime_event.

Stored context includes the original event envelope, integration_id, received_at, vessel_id, port_call_id, and event_type.

The ledger survives API process restart.
Demo reset does not erase integration evidence.

## Coordination contract

Contract id: portflow.coordination.v1

Endpoint:

    GET /api/v1/integration/port-calls/{call_id}/coordination

The integration must be authorized for the vessel attached to the requested port call.

The response includes port-call identity, vessel and berth, arrival/departure ETA, delay/risk, stage dependencies, service steps, active incidents, recovery proposals, and the advisory/no-actuation flags.

Recovery proposals remain normal Shorefront proposals with requires_approval=true.

## Contract discovery

Endpoint:

    GET /api/v1/integration/contracts

The response publishes contract version ids, supported event types, HTTP binding, reserved future Kafka semantics, safety invariants, and generated JSON schemas.

A future Kafka transport must carry the same portflow.vessel-event.v1 envelope rather than inventing a second semantic contract.

## Failure and replay behavior

Inbound delivery is at-least-once compatible because event_id is idempotent.

Network retry is safe when the exact same envelope is resent.

Out-of-order events are preserved; consumers use occurred_at and source-local sequence according to domain rules.

Unknown vessels return 404.
A valid integration attempting another integration's vessel returns 403.
A port-call/vessel mismatch returns 409.
Oversized normalized events return 413.
Conflicting event-id reuse returns 409.

## Versioning rule

Breaking envelope changes require a new contract id such as portflow.vessel-event.v2 or portflow.coordination.v2.

Do not silently reinterpret an existing version.

Transport changes alone do not require a semantic version change if the envelope meaning remains identical.

## Explicit non-goals for Shorefront

Shorefront is not a ship autopilot, DP controller, engine controller, raw NMEA/fieldbus recorder, machinery PLC replacement, bridge decision replacement, or vessel-side perception stack.

Those capabilities, if ever built, belong in the separate vessel-runtime repository with its own safety architecture.


## Reconciled parallel hash-cursor prototype

A parallel main-branch prototype explored a second batch envelope with source-sequence cursors and hash-chain heads.

That prototype is intentionally not exposed as a second Shorefront transport contract because it would duplicate the semantic boundary already defined by portflow.vessel-event.v1.

The useful idea is preserved as a vessel-runtime-side design candidate:

- maintain a local append-only source ledger
- track source-local monotonic sequence
- bind source entries to hashes
- project only privacy-approved normalized events into Shorefront
- use event_id idempotency at the Shorefront boundary

If implemented, the vessel runtime may use its own hash-chain internally while still emitting the stable portflow.vessel-event.v1 envelope to Shorefront.

## v0.16 human-visible crew exception lifecycle

Maritime Runtime v0.0.78 uses the existing portflow.vessel-event.v1 constraint
event without expanding the contract schema. Crew-private evidence remains
vessel-owned.

Shorefront stores the normalized privacy-minimized lifecycle through the machine
integration credential and exposes a separate human-authenticated reduced view
at:

    GET /api/v1/operations/vessel-exceptions

Authority remains separated:

    vessel integration credential
      -> may submit allowlisted vessel events
      -> cannot read the human operational exception view
      -> cannot approve recovery

    human viewer/operator/supervisor credential
      -> may inspect reduced exception state
      -> does not receive raw crew evidence or vessel integration secrets

The reduced view accepts only validated crew_operational_exception lifecycle
events with privacy_minimized=true, advisory_only=true,
execution_authorized=false and empty evidence_refs.

The exception_ref is a pseudonymous continuity handle generated onboard. It is
not a crew identity and does not expose the private task, actor, discrepancy,
override reason, or resolution reason.
