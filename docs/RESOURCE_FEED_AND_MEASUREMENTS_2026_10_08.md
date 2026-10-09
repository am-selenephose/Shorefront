# Shorefront V2: real-source contract, allocations and outcome measurements

This increment extends the existing **authenticated operational** API. It does
not certify that any real-world AIS, PCS or TOS provider is connected. A live
provider requires an executed data agreement, credentials, mapping and acceptance.

## Specific time-bounded resource-to-call allocation

Every resource assignment is a versioned, auditable record with a fixed
call_id, fixed resource_id, starts_at/ends_at UTC timestamps, status
(proposed/confirmed/released), confirmation_note and release_note. All
references must be effective and share a port. Windows must be ordered. A
confirmed assignment requires a recorded human confirmation note, a currently
available resource and no overlapping confirmed reservation of that resource.
Released assignments cannot be reopened or relabeled for another call/resource.

Connections can authorize a provider source to write resource_assignment
records. The machine bearer is limited to **proposed** state, never a forged
human confirmation or release. An administrator can revoke/rotate/expire that
source at any time. Idempotent atomic ingestion is already implemented in the
operational API. A source's last successful intake is an **ingestion receipt**
only; it does not validate AIS observation age or marine data accuracy.
The Connections UI warns when no ingest was recorded in the past 60 minutes.
This threshold is descriptive and is not a provider-specific SLA.

An upstream adapter with signed provider access and its own legal entitlement
should POST normalized records to:

  /api/v1/integrations/{source_id}/records

using a one-time admin-issued bearer token plus an Idempotency-Key. Minimal
example body (only a proposed assignment, no fake dispatch approval):

    {
      "records": [{
        "kind": "resource_assignment",
        "record_id": "stable-provider-allocation-id",
        "expected_revision": 0,
        "payload": {
          "call_id": "known-call-id",
          "resource_id": "known-resource-id",
          "starts_at": "2026-11-25T08:45:00Z",
          "ends_at": "2026-11-25T10:00:00Z",
          "status": "proposed"
        }
      }]
    }

The named operator confirms using the operational Records editor after
verifying the upstream person's authority and allocation window. An external
source may not do that by merely sending status=confirmed.

## Connected product behavior

Plan: specific allocation register by call, resource, window, status and
source, plus a create/edit action.

Readiness: separate check for explicitly confirmed call-resource allocations
and conflicts when a confirmed assigned resource is later unavailable.

What-If and Recovery: source-backed list of allocations, unresolved
availability and double-booking conflicts, and a missing-input warning if
a plan change requires resource re-confirmation. A confirmed conflict rejects
a decision alternative. Supervisor approval still checks the evidence ledger.

Connections: grant/revoke/rotate source privileges by record kind, show
last successful ingestion receipts, warn when a source has not pushed records
for over one hour, and preserve source attribution. No sample vessel data is
created in the live operational runtime.

## Measured outcomes, not invented cost savings

An authenticated user can GET /api/v1/decision-intelligence/outcomes. It
reports the count of approved decisions with and without a recorded observation,
coverage percentage and actual-versus-approved arrival/departure/occupancy
deviations. Each observation exposes the named source, time, record ID and
revision. The Recovery workspace shows this report.

This is *descriptive measurement*, not a trained delay predictor, causal
savings estimate, navigational clearance or evidence that upstream data are
independent. Missing observations are not treated as zeros.

## External integration acceptance, still required

1. Obtain authorization for one real AIS/TOS/PCS/pilot or tug data source.
2. Map real provider IDs and schema to the normalized Shorefront contract.
3. Verify provider observation timestamps, signed identity and freshness,
   plus duplicate, replay, outage and out-of-order revisions.
4. Perform a supervised real-port allocation and decision with recorded
   provider/operator evidence.
5. Collect actual observed outcomes and validate any optimization model
   against prospective data before claiming superior port performance.

Until then: advisory_only=true, production_ready=false. No automatic terminal
or vessel actuation; do not market real feeds or predictive savings as live.
