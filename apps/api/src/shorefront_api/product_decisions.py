"""Evidence-bound, human-approved scheduling proposals; never vessel clearance."""
from copy import deepcopy
from datetime import datetime
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import Column, String, Table, Text, insert, select, update

from .product_coordination import schedule_conflicts
from .product_models import RecordCommand, now, stamp
from .product_store import canonical, commands, digest, metadata

packets = Table('sf_decision_packet', metadata, Column('id', String(96), primary_key=True),
                Column('payload', Text, nullable=False), Column('receipt', Text, nullable=True))


def recall(connection, actor, key, intent):
    previous = connection.execute(select(commands).where(commands.c.actor_id == actor['id'], commands.c.key == key)).mappings().first()
    if previous:
        if previous['digest'] != intent:
            raise HTTPException(409, 'Idempotency key already belongs to another command')
        return json.loads(previous['response'])
    return None


def remember(connection, actor, key, intent, response):
    connection.execute(insert(commands).values(actor_id=actor['id'], key=key, digest=intent, response=canonical(response)))
    return response


def create_packet(store, connection, actor, request, key):
    if actor['role'] not in {'operator', 'supervisor', 'admin'}:
        raise HTTPException(403, 'Operational write permission required')
    intent = digest(canonical({'decision': request.model_dump(mode='json')}))
    replay = recall(connection, actor, key, intent)
    if replay is not None:
        return replay
    inputs = store.snapshot(connection)
    call = next((r for r in inputs if r['kind'] == 'call' and r['record_id'] == request.call_id), None)
    if not call or call['payload']['status'] != 'planned':
        raise HTTPException(422, 'Select an existing planned call')
    current = call['payload']
    port_berth = next((r for r in inputs if r['kind'] == 'berth' and r['record_id'] == current['berth_id']), None)
    options = []

    def option(label, body):
        projected = deepcopy(inputs)
        target = next(r for r in projected if r['kind'] == 'call' and r['record_id'] == request.call_id)
        target['payload'] = body
        conflicts = [c for c in schedule_conflicts(projected) if request.call_id in c['record_ids']]
        if not body['berth_id']:
            conflicts.append({'kind': 'unassigned_berth', 'explanation': 'A recorded berth is required', 'record_ids': [request.call_id]})
        options.append({'id': f'option-{len(options)}', 'label': label, 'call_payload': body,
                        'eligible': not conflicts, 'rejected_reasons': [c['explanation'] for c in conflicts],
                        'shift_minutes': (datetime.fromisoformat(body['eta']) - datetime.fromisoformat(current['eta'])).total_seconds() / 60})

    option('Keep recorded plan', deepcopy(current))
    duration = datetime.fromisoformat(current['etd']) - datetime.fromisoformat(current['eta'])
    berths = [r for r in inputs if r['kind'] == 'berth' and port_berth and r['payload']['port_id'] == port_berth['payload']['port_id']]
    # Bound the proposal set; the interface does not claim global optimization.
    for berth in sorted(berths, key=lambda r: (r['record_id'] != current['berth_id'], r['record_id']))[:8]:
        start = datetime.fromisoformat(current['eta'])
        occupied = [r['payload'] for r in inputs if r['kind'] == 'call' and r['record_id'] != request.call_id
                    and r['payload']['status'] not in {'departed', 'cancelled'}
                    and (r['payload']['berth_id'] == berth['record_id'] or r['payload']['vessel_id'] == current['vessel_id'])]
        for other in sorted(occupied, key=lambda c: datetime.fromisoformat(c['eta'])):
            if start < datetime.fromisoformat(other['etd']) and start + duration > datetime.fromisoformat(other['eta']):
                start = datetime.fromisoformat(other['etd'])
        body = {**current, 'berth_id': berth['record_id'], 'eta': start.isoformat(), 'etd': (start + duration).isoformat()}
        if berth['record_id'] != current['berth_id'] or start != datetime.fromisoformat(current['eta']):
            option(f"Earliest recorded slot · {berth['payload']['name']}", body)
    packet = {'id': str(uuid4()), 'created_at': stamp(now()), 'created_by': actor['id'],
              'question': request.question, 'call_id': request.call_id, 'call_revision': call['revision'],
              'input_digest': digest(canonical(inputs)), 'inputs': inputs, 'options': options,
              'trust': {'confidence': 'uncalibrated', 'basis': 'Customer-recorded schedule and dimensions only',
                        'source_count': len(set(r['source'] for r in inputs)),
                        'warnings': ['Weather, tide, under-keel clearance, actual availability and navigational safety are not validated.',
                                     'The duration is the recorded plan, not a learned prediction.',
                                     'Approval updates a plan; it is not vessel clearance, external agreement or actual savings.']},
              'receipt': None}
    connection.execute(insert(packets).values(id=packet['id'], payload=canonical(packet), receipt=None))
    store.add_audit(connection, actor['id'], 'decision.proposed', {'decision_id': packet['id'], 'input_digest': packet['input_digest'], 'packet_digest': digest(canonical(packet))})
    return remember(connection, actor, key, intent, packet)


def get_packet(connection, packet_id):
    row = connection.execute(select(packets).where(packets.c.id == packet_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Decision packet not found')
    result = json.loads(row['payload'])
    result['receipt'] = json.loads(row['receipt']) if row['receipt'] else None
    return result


def approve_packet(store, connection, actor, packet_id, request):
    if actor['role'] != 'supervisor':
        raise HTTPException(403, 'A supervisor must review and approve the recorded plan')
    # Fail closed on ordinary stored-data corruption before an approval can use
    # altered choices. This checksum gate is not a digital signature or a defence
    # against an administrator replacing the database and its entire audit chain.
    try:
        intact = store.evidence(connection)['audit_valid']
    except (ValueError, KeyError, TypeError):
        intact = False
    if not intact:
        raise HTTPException(409, 'Evidence integrity check failed; ask the installation operator to investigate before approval')
    packet = get_packet(connection, packet_id)
    receipt = packet['receipt']
    if receipt:
        if receipt['approved_by'] == actor['id'] and receipt['option_id'] == request.option_id and receipt['reason'] == request.reason:
            return receipt
        raise HTTPException(409, 'This decision already has a different approval')
    inputs = store.snapshot(connection)
    if digest(canonical(inputs)) != packet['input_digest']:
        raise HTTPException(409, 'Operational facts changed; create and review a new decision packet')
    option = next((o for o in packet['options'] if o['id'] == request.option_id), None)
    if not option or not option['eligible']:
        raise HTTPException(422, 'Select an eligible option after reviewing its limitations')
    result = store.write_record(connection, actor, 'call', RecordCommand(record_id=packet['call_id'],
        expected_revision=packet['call_revision'], source=f"Approved decision {packet_id}", payload=option['call_payload']), f'decision-{packet_id}')
    receipt = {'decision_id': packet_id, 'option_id': request.option_id, 'reason': request.reason,
               'approved_by': actor['id'], 'approved_at': stamp(now()), 'input_digest': packet['input_digest'],
               'resulting_revision': result['revision'], 'effect': 'recorded_plan_updated', 'cash_saved': None}
    connection.execute(update(packets).where(packets.c.id == packet_id).values(receipt=canonical(receipt)))
    store.add_audit(connection, actor['id'], 'decision.approved', receipt)
    return receipt
