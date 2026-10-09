# Pre-rename evidence fixture

`pre_rename_evidence.json` was captured from the original package at commit
`603398fa4cc3360ee3ff53ad89c0437292a5b1c8` on 2 October 2026.
It contains only synthetic simulator data, not customer or live-port information.

The baseline package's clock was fixed to `2026-10-02T12:00:00Z`. A fresh
`HarborSimulator().overview()` supplied the snapshot. A `ScenarioRunEvidence`
model was constructed with that snapshot and the baseline `berth-crunch` scenario
definition; the scenario was **not executed**. The expected evidence SHA-256 was
computed over its JSON-mode model dump with sorted keys and compact separators.
The expected recovery fingerprint came from the baseline simulator restored from
that same snapshot for `pc-aurora`.

Tests use literal captured expectations, not the renamed code to recompute its
own oracle. They check model/storage round trips, preserved historical labels and
events, evidence export hash, and restored recovery fingerprint. They supplement,
not replace, existing scenario execution and event idempotency tests.
