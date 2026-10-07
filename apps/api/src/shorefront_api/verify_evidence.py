"""Offline consistency verifier for Shorefront exports; no database or network.

Run this file directly with Python 3, or use ``python -m
shorefront_api.verify_evidence``. A valid hash chain is NOT a signature. An
optional root from a separately trusted record pins the exact exported history.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

MAX_BYTES = 64 * 1024 * 1024


class InvalidEvidence(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidEvidence(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def parse_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result, 'Duplicate JSON object key')
            result[key] = item
        return result

    def reject_constant(_):
        raise InvalidEvidence('Non-finite JSON value')

    return json.loads(value, object_pairs_hook=unique, parse_constant=reject_constant)


def record_key(record):
    require(isinstance(record, dict), 'Malformed record')
    require(isinstance(record['kind'], str) and isinstance(record['record_id'], str), 'Malformed record identity')
    require(type(record['revision']) is int and record['revision'] > 0, 'Malformed record revision')
    return record['kind'], record['record_id'], record['revision']


def verify(data, *, installation, expected_root=None):
    """Recompute assurance locally; never trust the exported audit_valid flag."""
    try:
        require(isinstance(data, dict), 'Expected an evidence object')
        require(bool(installation) and data['installation_id'] == installation, 'Installation does not match')
        require(all(isinstance(data[key], list) for key in ('audit', 'versions', 'decisions')), 'Missing evidence lists')
        previous = '0' * 64
        last_sequence = 0
        written, proposed, approved, detected_conflicts, resolved_conflicts = {}, {}, {}, {}, {}
        for row in data['audit']:
            require(type(row['sequence']) is int and row['sequence'] > last_sequence, 'Audit order is invalid')
            last_sequence = row['sequence']
            require(row['previous_hash'] == previous, 'Audit chain is broken')
            require(isinstance(row['payload'], str), 'Malformed audit payload')
            require(row['hash'] == digest(previous + row['payload']), 'Audit payload hash does not match')
            previous = row['hash']
            event = parse_json(row['payload'])
            action, detail = event['action'], event['detail']
            if action == 'record.written':
                key = record_key(detail)
                require(key not in written, 'Duplicate record audit entry')
                written[key] = detail
            elif action == 'decision.proposed':
                key = detail['decision_id']
                require(key not in proposed, 'Duplicate decision audit entry')
                proposed[key] = detail['packet_digest']
            elif action == 'decision.approved':
                key = detail['decision_id']
                require(key not in approved, 'Duplicate decision approval')
                approved[key] = detail
            elif action == 'fact.conflict.detected':
                key = detail['id']
                require(key not in detected_conflicts, 'Duplicate fact conflict detection')
                detected_conflicts[key] = detail
            elif action == 'fact.conflict.resolved':
                key = detail['id']
                require(key not in resolved_conflicts, 'Duplicate fact conflict resolution')
                resolved_conflicts[key] = detail
        require(data['audit_root'] == previous, 'Exported audit root does not match')
        if expected_root is not None:
            require(isinstance(expected_root, str) and re.fullmatch('[0-9a-f]{64}', expected_root), 'Expected root must be a SHA-256 hex digest')
            require(previous == expected_root, 'Trusted audit root does not match')
        observed = set()
        last_sequence = 0
        for record in data['versions']:
            key = record_key(record)
            require(key not in observed, 'Duplicate exported record')
            observed.add(key)
            require(type(record['sequence']) is int and record['sequence'] > last_sequence, 'Record order is invalid')
            last_sequence = record['sequence']
            require(key in written and canonical(record) == canonical(written[key]), 'Record differs from audited evidence')
        require(observed == set(written), 'Missing exported record')
        exported_records = {record_key(record): record for record in data['versions']}
        conflicts = data.get('conflicts', [])
        require(isinstance(conflicts, list), 'Malformed conflict export')
        observed_conflicts = set()
        for conflict in conflicts:
            require(isinstance(conflict, dict), 'Malformed fact conflict')
            conflict_id = conflict['id']
            require(isinstance(conflict_id, str) and conflict_id not in observed_conflicts, 'Duplicate or malformed fact conflict')
            observed_conflicts.add(conflict_id)
            detected = {'id': conflict_id, 'kind': conflict['kind'], 'record_id': conflict['record_id'],
                        'baseline_revision': conflict['baseline_revision'],
                        'challenger_revision': conflict['challenger_revision'], 'fields': conflict['fields']}
            require(detected_conflicts.get(conflict_id) == detected, 'Fact conflict differs from audited detection')
            baseline_key = record_key(conflict['baseline'])
            challenger_key = record_key(conflict['challenger'])
            require(exported_records.get(baseline_key) == conflict['baseline'], 'Fact conflict baseline differs from exported version')
            require(exported_records.get(challenger_key) == conflict['challenger'], 'Fact conflict challenger differs from exported version')
            require(baseline_key == (conflict['kind'], conflict['record_id'], conflict['baseline_revision']), 'Fact conflict baseline identity mismatch')
            require(challenger_key == (conflict['kind'], conflict['record_id'], conflict['challenger_revision']), 'Fact conflict challenger identity mismatch')
            resolution = resolved_conflicts.get(conflict_id)
            if conflict['state'] == 'resolved':
                expected = {'id': conflict_id, 'kind': conflict['kind'], 'record_id': conflict['record_id'],
                            'accepted_revision': conflict['accepted_revision'],
                            'resolution_revision': conflict['resolution_revision'],
                            'note': conflict['resolution_note']}
                require(resolution == expected, 'Fact conflict resolution differs from audited resolution')
            else:
                require(resolution is None, 'Unresolved fact conflict has a resolution audit event')
        require(observed_conflicts == set(detected_conflicts), 'Missing exported fact conflict')
        require(set(resolved_conflicts).issubset(observed_conflicts), 'Resolution has no exported fact conflict')
        observed = set()
        for packet in data['decisions']:
            key = packet['id']
            require(isinstance(key, str) and key not in observed, 'Duplicate or malformed exported decision')
            observed.add(key)
            require(proposed.get(key) == digest(canonical({**packet, 'receipt': None})), 'Decision differs from audited evidence')
            require(packet['input_digest'] == digest(canonical(packet['inputs'])), 'Decision input fingerprint does not match')
            require(canonical(approved.get(key)) == canonical(packet['receipt']), 'Approval differs from audited evidence')
        require(observed == set(proposed), 'Missing exported decision')
        require(set(approved).issubset(observed), 'Approval has no exported decision')
        return {'valid': True, 'versions': len(written), 'decisions': len(proposed), 'conflicts': len(detected_conflicts),
                'audit_entries': len(data['audit']), 'audit_root': previous, 'signed': False,
                'root_pinned': expected_root is not None,
                'assurance': 'Internal consistency only; not signer identity, external timestamp or proof of physical events.'}
    except InvalidEvidence as error:
        return {'valid': False, 'reason': str(error), 'signed': False}
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
        return {'valid': False, 'reason': 'Malformed or incomplete evidence', 'signed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--installation', required=True, help='Expected installation ID from a trusted inventory')
    parser.add_argument('--expected-root', help='Optional SHA-256 audit root retained separately from the export')
    args = parser.parse_args()
    try:
        with args.file.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, 'Evidence file exceeds the 64 MiB verification limit')
        result = verify(parse_json(raw.decode('utf-8')), installation=args.installation, expected_root=args.expected_root)
    except (OSError, ValueError, RecursionError):
        result = {'valid': False, 'reason': 'Unreadable, oversized or invalid JSON evidence', 'signed': False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
