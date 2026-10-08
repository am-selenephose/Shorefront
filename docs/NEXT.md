# Next work for Shorefront

The current product is Shorefront, with its own operational runtime, stable public
hostname and release lifecycle. Follow RENAMING_AND_UPGRADING.md for existing
state and consumers. Do not infer a completed customer deployment from source
changes or a passing local release gate.

## Current commercial release gates

1. **Prove the first buyer and paid workflow.** Run one complete real port-call
   workflow with a design partner, measure operator task completion and record
   concrete acceptance evidence. Build only the missing workflow revealed by that
   use, rather than adding speculative modules.

2. **Connect one real operational source under contract.** Validate licensing,
   schema, freshness, outage/error behavior, replay rules, provenance and recovery
   before calling any feed live. The existing generic ingestion, DCSA subset and
   reconciliation machinery are infrastructure, not proof of a vendor integration.

3. **Define enterprise identity requirements.** Dedicated-installation accounts,
   invitations and roles are implemented. Add OIDC/SAML/federated identity only
   against a real buyer requirement and acceptance test.

4. **Qualify production operations.** The host has private operational metrics,
   a five-minute health timer, daily backups and a verified isolated restore.
   Remaining work is explicit RTO/RPO, encrypted/off-site backup policy, retention
   sizing, load/capacity testing, history/evidence growth qualification and a
   multi-host/HA decision if the commercial SLA requires it.

5. **Complete independent assurance.** Run an independent security/code review,
   Firefox/WebKit acceptance, accessibility review and failure-mode exercises.
   Chromium regression coverage is extensive but is not cross-engine certification.

6. **Strengthen evidence only where the buyer needs it.** The audit chain and
   offline verifier detect ordinary corruption and preserve provenance. External
   signatures, trusted timestamps and enterprise key custody remain separate from
   the current evidence model.

7. **Expand standards/vendor surfaces from evidence, not ambition.** DCSA support
   remains subset-not-certified. Add further DCSA events, TOS/PCS/AIS/weather
   adapters and outbound delivery/retry infrastructure only for contracted
   workflows.

## Completed infrastructure that should not be reopened speculatively

- dedicated operational runtime and PostgreSQL ownership boundary;
- authenticated roles, invitations, password rotation/recovery and origin checks;
- typed records, two-clock history, evidence export and offline verification;
- decision packets with explicit human approval and bounded recorded-input checks;
- geographic map, berth horizon, coordination and source reconciliation;
- authenticated call readiness coverage analysis and read-only berth/time what-if planning;
- scoped inbound sources, partner projections/deliveries and DCSA subset gateway;
- full operational/training browser regression jobs and disposable PostgreSQL CI;
- real Nginx HTTP/TLS delivery regression tests;
- private operational metrics, health timer and scheduled backups;
- stable shorefront.animantum.com named-tunnel ingress;
- isolated restore rehearsal of the latest live backup.

The vessel runtime remains a separate system. Shorefront accepts
privacy-minimized normalized events and produces advisory coordination. Do not
introduce physical actuation, crew-private records or a competing semantic
contract here.

## Optional US water-level context (new local implementation)

The local branch adds operator-selected NOAA CO-OPS station data as a separate read-only
context panel, disabled by default unless `SHOREFRONT_NOAA_ENABLED=1` is configured.
The 7-digit station is recorded on a Port; provider data is time-labeled,
source-attributed, and can become stale/unavailable. This is not navigational
clearance and cannot authorize a berth movement. The workspace now also offers
an explicit Refresh control for out-of-band record changes. These additions
are local development work until release verification and an approved cutover.
