"""Advisory, transactional-readonly schedule preview. Never writes to customer records."""
from datetime import datetime
from fastapi import HTTPException
from pydantic import AwareDatetime, model_validator

from .product_models import Identifier, Call, StrictModel
from .product_coordination import schedule_conflicts


class WhatIf(StrictModel):
    call_id: Identifier
    berth_id: Identifier | None
    eta: AwareDatetime
    etd: AwareDatetime

    @model_validator(mode='after')
    def ordered(self):
        if self.etd <= self.eta:
            raise ValueError('Proposed departure must be after arrival')
        return self


def compare_plan(records, proposed: WhatIf, read_at: str):
    lookup = {(record['kind'], record['record_id']): record for record in records}
    call = lookup.get(('call', proposed.call_id))
    if call is None:
        raise HTTPException(404, 'Recorded port call not found')
    if call['payload']['status'] in {'departed', 'cancelled'}:
        raise HTTPException(409, 'Closed calls cannot be revised through what-if planning')
    vessel = lookup.get(('vessel', call['payload']['vessel_id']))
    berth = lookup.get(('berth', proposed.berth_id)) if proposed.berth_id else None
    if proposed.berth_id and berth is None:
        raise HTTPException(422, 'Proposed berth must already exist in this installation')
    original_berth = lookup.get(('berth', call['payload'].get('berth_id')))
    if original_berth and berth and original_berth['payload']['port_id'] != berth['payload']['port_id']:
        raise HTTPException(422, 'Proposed berth belongs to a different port; create a separate port call')

    # Reuse the exact persisted call validation rules for uncommitted proposals.
    candidate = Call.model_validate({
        **call['payload'],
        'berth_id': proposed.berth_id,
        'eta': proposed.eta,
        'etd': proposed.etd,
    }).model_dump(mode='json')
    alternate = [{**record, 'payload': candidate} if
                 record['kind'] == 'call' and record['record_id'] == proposed.call_id else record
                 for record in records]

    def individual_conflicts(snapshot):
        return [conflict for conflict in schedule_conflicts(snapshot)
                if proposed.call_id in conflict['record_ids']]

    def berth_name(berth_id):
        current = lookup.get(('berth', berth_id)) if berth_id else None
        return current['payload']['name'] if current else None

    original = call['payload']
    return {
        'call_id': proposed.call_id,
        'vessel_name': vessel['payload']['name'] if vessel else 'Unidentified vessel',
        'source': call['source'],
        'known_at': call['known_at'],
        'read_at': read_at,
        'read_only': True,
        'baseline': {'berth_id': original.get('berth_id'),
                     'berth_name': berth_name(original.get('berth_id')),
                     'eta': original['eta'], 'etd': original['etd'],
                     'conflicts': individual_conflicts(records)},
        'candidate': {'berth_id': candidate['berth_id'],
                      'berth_name': berth_name(candidate['berth_id']),
                      'eta': candidate['eta'], 'etd': candidate['etd'],
                      'conflicts': individual_conflicts(alternate)},
        'change': {
            'berth_changed': candidate['berth_id'] != original.get('berth_id'),
            'eta_minutes': round((proposed.eta - datetime.fromisoformat(original['eta'])).total_seconds() / 60),
            'etd_minutes': round((proposed.etd - datetime.fromisoformat(original['etd'])).total_seconds() / 60),
        },
        'boundary': 'Recorded constraints only; no navigation, weather, tides, UKC or operational permission.',
    }
