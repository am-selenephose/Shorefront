"""Named-party lifecycle rules and deterministic recorded-schedule checks."""
from datetime import datetime
from itertools import combinations

from fastapi import HTTPException


def authorize_transition(kind, actor, payload, latest, creator_id):
    if kind not in {'handoff', 'commitment', 'obligation'}:
        return
    initial = {'handoff': 'prepared', 'commitment': 'proposed', 'obligation': 'draft'}[kind]
    state = payload['status']
    if latest is None:
        if state != initial:
            raise HTTPException(409, f'New {kind} must start as {initial}')
        return
    previous = latest['payload']
    old_state = previous['status']
    allowed = {
        'handoff': {'prepared': {'prepared', 'sent'}, 'sent': {'acknowledged'}},
        'commitment': {'proposed': {'proposed', 'accepted', 'declined', 'cancelled'}, 'accepted': {'fulfilled', 'cancelled'}},
        'obligation': {'draft': {'draft', 'active', 'cancelled'}, 'active': {'active', 'completed', 'cancelled'}},
    }[kind]
    if state not in allowed.get(old_state, set()):
        raise HTTPException(409, f'{kind} cannot transition from {old_state} to {state}; terminal records are sealed')
    if kind == 'obligation':
        if actor['id'] not in {creator_id, previous['assignee_id']} and actor['role'] not in {'admin', 'supervisor'}:
            raise HTTPException(403, 'Only the responsible party or supervisor may change this obligation')
        return
    recipient_action = state in {'acknowledged', 'accepted', 'declined', 'fulfilled'}
    permitted = previous['recipient_id'] if recipient_action else creator_id
    if actor['id'] != permitted:
        raise HTTPException(403, 'This transition requires the named recipient' if recipient_action else 'This transition requires the originating party')
    if recipient_action or old_state != initial:
        fixed = {k: v for k, v in previous.items() if k not in {'status', 'proof'}}
        if any(payload[k] != v for k, v in fixed.items()):
            raise HTTPException(409, 'Sent or accepted terms cannot be rewritten; create a new record')


def schedule_conflicts(records):
    facts = {(r['kind'], r['record_id']): r['payload'] for r in records}
    calls = [r for r in records if r['kind'] == 'call' and r['payload']['status'] not in {'departed', 'cancelled'}]
    conflicts = []
    for first, second in combinations(calls, 2):
        a, b = first['payload'], second['payload']
        if max(datetime.fromisoformat(a['eta']), datetime.fromisoformat(b['eta'])) >= min(datetime.fromisoformat(a['etd']), datetime.fromisoformat(b['etd'])):
            continue
        kinds = []
        if a['berth_id'] and a['berth_id'] == b['berth_id']:
            kinds.append(('berth_overlap', 'Recorded occupancy intervals overlap on the same berth'))
        if a['vessel_id'] == b['vessel_id']:
            kinds.append(('vessel_overlap', 'The same vessel has overlapping active calls'))
        for kind, explanation in kinds:
            conflicts.append({'kind': kind, 'record_ids': [first['record_id'], second['record_id']], 'explanation': explanation})
    for call in calls:
        body = call['payload']
        berth = facts.get(('berth', body['berth_id']), {})
        vessel = facts.get(('vessel', body['vessel_id']), {})
        for measurement in ('length_m', 'draft_m'):
            limit, actual = berth.get('max_' + measurement), vessel.get(measurement)
            if limit is not None and actual is not None and actual > limit:
                conflicts.append({'kind': 'berth_limit', 'record_ids': [call['record_id']], 'explanation': f'Recorded vessel {measurement} exceeds the recorded berth limit'})
    return conflicts
