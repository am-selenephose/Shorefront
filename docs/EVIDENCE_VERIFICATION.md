# Check an exported evidence file offline

Shorefront exports operational evidence from **Evidence → Export evidence**.
The standalone verifier recomputes the audit chain and checks that every exported
record, decision input/option and approval matches its audited counterpart. It
also rejects missing or duplicate items. It does not trust `audit_valid` supplied
inside the file and does not connect to the application, database or network.

Run with Python 3 from the repository root:

```sh
python3 apps/api/src/shorefront_api/verify_evidence.py /secure/shorefront-evidence.json \
  --installation your-recorded-installation-id
```

Use the installation ID from your separately retained installation inventory,
not blindly copied from an untrusted export. The command prints a JSON summary
without record payloads. Exit code `0` means all implemented checks passed;
exit code `1` means verification failed. Invalid command-line arguments use
Python argparse's normal exit code `2`. Input files are limited to 64 MiB.
Duplicate JSON keys and non-finite numbers are rejected.

For comparison against a root you previously retained through a trusted channel:

```sh
python3 apps/api/src/shorefront_api/verify_evidence.py /secure/shorefront-evidence.json \
  --installation your-recorded-installation-id \
  --expected-root YOUR_PREVIOUSLY_RETAINED_64_CHARACTER_SHA256
```

The expected root must match this exact export snapshot. A later legitimate
change produces a different root. Keep the original export and root together in
your controlled record-retention process. Never publish evidence containing
customer or employee information merely to demonstrate that a check passed.

## What a pass does not establish

- A consistent chain is **not a digital signature**, proof of signer identity,
  an externally trusted timestamp, or evidence that a physical event happened.
- Someone able to replace both the database and its entire chain can create a
  different internally consistent export. A root supplied by that same person
  in the same file provides no independent trust anchor.
- Without a separately trusted root, this checker cannot detect replacement of
  the entire history with another consistent history or a self-consistent prefix.
- Source licensing, legal meaning, navigational clearance and causal financial
  savings are not verified.
- The format is the current operational evidence export, not a DCSA/S-211
  conformance declaration or a signed interchange standard.

The verifier uses the same documented canonical JSON convention as the producer:
sorted keys, compact separators, UTF-8, and no non-finite numbers. It runs without
Shorefront's Python dependencies when invoked by its file path.
