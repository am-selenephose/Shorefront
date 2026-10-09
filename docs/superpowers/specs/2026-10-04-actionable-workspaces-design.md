# Shorefront actionable operational workspaces

## Intent and scope

Continue the owner-approved operational programme in the existing clean Shorefront
checkout. The owner explicitly requested continuous execution, not repeated approval
handoffs. The current dashboard at `f1c3a05` exposes durable data but leaves most work
behind a generic record editor. This increment closes that usability gap; it does not
claim completion of the twenty-system infrastructure programme.

The product is a private-installation maritime coordination workspace for operators,
named recipients and supervisors. Success is a real recorded call progressing through
an assigned action, commitment or handoff to evidence-backed completion without editing
raw statuses or fabricating observations. Preserve `brand.md`, cream-first theme and
remembered night mode. No customer data is inserted into the supplied tunnel.

## Chosen approach

Keep the existing transactional record authority and extend its user-facing workflows.
A second workflow database would split evidence; a visual-only reskin would leave the
same dead ends. Use named workspaces and contextual record actions over the current API.
The server must describe permitted coordination actions using the same rules that enforce
them. A projection is guidance, never an authorization token; writes recheck authority.

1. **First-use checklist and contextual actions:** Pulse explains the port → berth/vessel
   → call path with working actions. Calls, timeline and exception records can open the
   correct editor in context. Creating a linked task preserves its call/incident links.
   Empty states contain a usable next step, not only instructions to find Records.
2. **Coordination desk:** commitments, handoffs and reviewed obligations show originating
   party, recipient/assignee, due date, source and current state. Filters for open/all/my
   actions and call context. Only server-permitted transitions are offered. Transition
   forms preserve every existing field byte-for-byte except explicit state/proof/review
   changes, require source and completion evidence, retain input on error, and disable
   writes offline. No external delivery or legal interpretation is claimed.
3. **Historical evidence:** reconstruct both clocks and inspect full payloads, source,
   actor and versions; compare the reconstructed facts with the current recorded view.
   Asynchronous results cannot replace a newer selection. Keep historical views read-only.
4. **Operational clarity:** show complete counts and overflow links, expose existing
   schedule conflicts in Plan, keep linked operational threads discoverable, and test
   both themes at 375/768/1280+ widths. No fake maps, resource geometry or savings.

## Boundaries and failure behavior

All reads use existing authenticated routes. Mutation authority, revision checks,
idempotency, Origin, CSRF and audit atomicity remain server enforced. Closed workflow
records stay sealed. Original terms and timestamp precision survive transition forms.
The UI must not imply successful writes until the API commits. Refresh failures are
distinguished from rejected saves. Unknown, stale and empty states remain explicit.

Licensed feeds, standards conformance, partner federation, signed external evidence,
counterfactual prediction and commercial claims/payment automation remain separate
unfinished systems. Do not relabel this increment as the final commercial release.

## Acceptance

- Empty installation guides a user into creating facts without simulator records.
- From Calls, create a linked incident/task and reopen its persisted details.
- Originator creates/sends a handoff; another named member acknowledges with proof;
  originator cannot acknowledge on their behalf; exact imported timestamp terms survive.
- Recipient accepts/fulfills a commitment; reviewer activates/completes an obligation;
  terminal records offer no further mutations; stale/offline transitions preserve input.
- Anonymous users cannot read workflow projections; viewers receive no actions.
- Historical reconstruction shows original field values and current differences, while
  history/export remain available. No historical view is presented as live.
- Existing account, import, decision, outcome, training and session safety tests pass.
