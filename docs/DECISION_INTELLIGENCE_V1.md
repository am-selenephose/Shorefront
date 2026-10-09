# Shorefront: Operational Decision Intelligence V1

Status: **released** as advisory operational software on 2026-10-08 from application source aa7f9f0. Full commercial readiness remains false; see [release receipt](RELEASE_DECISION_INTELLIGENCE_2026_10_08.md).

## End-to-end decision path

1. In authenticated Plan, choose a recorded active call and run the read-only berth/time comparison.
2. The scenario now includes source-aware operational impact: introduced/cleared conflicts, related recorded calls, open work, unavailable port-wide resources, missing evidence and explicit limitations.
3. For a planned call, explicitly **Save exact scenario for supervisor review**. The current berth, ETA and ETD become the operator-proposed alternative inside a new immutable decision packet. The live call does not change.
4. The new packet can open directly in Recovery. The review cards expose the operational impact for every bounded option, including the keep-original alternative.
5. An eligible option still needs a separately authenticated supervisor approval and written reason. The stored-input evidence digest must match current facts. An approval updates only the recorded plan and remains auditable.
6. Observed outcomes remain a separate, human-recorded post-operation artifact. No savings or live movement is inferred.

## What the algorithm actually does

- Uses the existing deterministic `schedule_conflicts` rules and recorded berth/vessel metadata.
- Enumerates bounded schedule alternatives from existing local berth records; it is not global optimization.
- Compares conflict identities before and after a proposal, and lists added/cleared conflicts.
- Identifies other recorded calls sharing berth or vessel and overlapping the original or candidate window.
- Preserves linked open tasks, incidents, handoffs, commitments and obligations as source-attributed review evidence.
- Lists unavailable **port-wide** resources without falsely assuming that a pilot/tug/crew/equipment resource is allocated to the selected call.
- Labels missing dimensions, geography/port context and resource allocation information; keeps confidence `uncalibrated`.
- Computes an evidence-oriented **review order**, never an autonomous recommendation or navigational clearance.

## Data and safety boundaries

No licensed AIS, weather, tide, under-keel clearance, vessel tracking, yard/crane dispatch, pilot allocation, external stakeholder agreement or historical predictive accuracy is established by this feature. No hypothetical call is automatically rescheduled. Decision packet creation is an explicit write of review evidence, not a call update. Source-fact reconciliation remains a separate human-owned process; external source disagreements must still be reviewed before relying on a decision.

## Release proof and known next gaps

The isolated branch is subject to full API and browser regression gates. The dedicated real-customer installation must not be seeded or modified for acceptance. Next capability work should add a qualified resource-to-call assignment contract, licensed provider freshness/error handling, and measured prediction calibration from actual outcomes, after a design partner validates those inputs.

## Source authority gate (follow-up hardening)

Human-reconciled source facts are a prerequisite for approval. What-if analysis
shows unresolved disagreements involving the target call, its vessel, original
or proposed berth/port, or related overlapping calls and their vessel/berth.
Decision packets freeze those disagreement identifiers and fields into each
option's review evidence; alternatives with relevant unresolved disagreements
are **not eligible**, even when the geometric schedule has no conflict.

At approval, the service rechecks unresolved conflicts within the transaction
rather than relying exclusively on the recorded version digest (reconciliation
state can change independently from the selected two-clock snapshot).
An unrelated vessel's disagreement does not block another port call.
Older stored packets remain readable; approval still uses the current gate.

Port-wide resource warnings are shown as uncertain context, not as a claim
that a specific tug/pilot/crew is assigned. This scope deliberately does not
provide qualified contractual source authority, resource allocations,
navigational clearance, prediction or autonomous dispatch.
