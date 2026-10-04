"""Named-party lifecycle rules and deterministic recorded-schedule checks."""
from datetime import datetime
from itertools import combinations

from fastapi import HTTPException


TRANSITIONS = {
    'handoff': {'prepared': {'prepared', 'sent'}, 'sent': {'acknowledged'}},
    'commitment': {'proposed': {'proposed', 'accepted', 'declined', 'cancelled'}, 'accepted': {'fulfilled', 'cancelled'}},
    'obligation': {'draft': {'draft', 'active', 'cancelled'}, 'active': {'active', 'completed', 'cancelled'}},
}
ACTION_LABELS = {
    'handoff': {'sent': 'Send handoff', 'acknowledged': 'Acknowledge handoff'},
    'commitment': {'accepted': 'Accept commitment', 'declined': 'Decline commitment',
                   'fulfilled': 'Fulfill commitment', 'cancelled': 'Cancel commitment'},
    'obligation': {'active': 'Activate obligation', 'completed': 'Complete obligation', 'cancelled': 'Cancel obligation'},
}


def same_term(key, first, second):
    # Different UTC offsets may express exactly the same instant. Never round it.
    if key == 'due_at':
        return datetime.fromisoformat(first) == datetime.fromisoformat(second)
    return first == second


def cancellation_preserves_party(kind, payload, latest, field):
    return (kind in {'commitment', 'obligation'} and latest is not None and
            payload['status'] == 'cancelled' and payload.get(field) == latest['payload'].get(field))


def participant_eligible(member):
    return bool(member and member['active'] and member['role'] in {'admin', 'operator', 'supervisor'})


def coordination_actions(record, actor, creator_id, members):
    if not participant_eligible(actor):
        return []
    kind, previous = record['kind'], record['payload']
    result = []
    for target, label in ACTION_LABELS[kind].items():
        if target == previous['status']:
            continue
        candidate = {**previous, 'status': target}
        field = 'assignee_id' if kind == 'obligation' else 'recipient_id'
        if not participant_eligible(members.get(previous[field])) and not cancellation_preserves_party(kind, candidate, record, field):
            continue
        try:
            authorize_transition(kind, actor, candidate, record, creator_id)
        except HTTPException:
            continue
        result.append({'status': target, 'label': label,
                       'requires_proof': target in {'acknowledged', 'fulfilled', 'completed'},
                       'requires_review': kind == 'obligation' and target in {'active', 'completed'}})
    return result


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
    allowed = TRANSITIONS[kind]
    if state not in allowed.get(old_state, set()):
        raise HTTPException(409, f'{kind} cannot transition from {old_state} to {state}; terminal records are sealed')
    if kind == 'obligation':
        if actor['id'] not in {creator_id, previous['assignee_id']} and actor['role'] not in {'admin', 'supervisor'}:
            raise HTTPException(403, 'Only the responsible party or supervisor may change this obligation')
        if old_state == 'active' and any(not same_term(k, payload[k], v) for k, v in previous.items()
                                         if k not in {'status', 'proof', 'review_note'}):
            raise HTTPException(409, 'Reviewed obligation terms cannot be rewritten; create a new draft')
        return
    recipient_action = state in {'acknowledged', 'accepted', 'declined', 'fulfilled'}
    permitted = previous['recipient_id'] if recipient_action else creator_id
    if actor['id'] != permitted:
        raise HTTPException(403, 'This transition requires the named recipient' if recipient_action else 'This transition requires the originating party')
    if recipient_action or old_state != initial:
        fixed = {k: v for k, v in previous.items() if k not in {'status', 'proof'}}
        if any(not same_term(k, payload[k], v) for k, v in fixed.items()):
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
