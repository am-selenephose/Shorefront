"""Recorded-data-only impact checks for a proposed call schedule."""
from datetime import datetime
from .product_coordination import schedule_conflicts

CLOSED = {'resolved','done','acknowledged','fulfilled','completed','cancelled','declined'}
RELATED = {'task','incident','handoff','commitment','obligation'}

def overlaps(a,b):
    return max(datetime.fromisoformat(a['eta']),datetime.fromisoformat(b['eta'])) < min(datetime.fromisoformat(a['etd']),datetime.fromisoformat(b['etd']))

def key(conflict):
    return (conflict['kind'],tuple(sorted(conflict['record_ids'])))

def relevant_source_disagreements(records, call_id, candidate, related, unresolved):
    # A disagreement is relevant only if it concerns a scheduled object being
    # assessed. Do not block an unrelated call or an unrelated port.
    by_id={(record['kind'],record['record_id']):record for record in records}
    current=by_id[('call',call_id)]['payload']
    referenced={('call',call_id),('vessel',current['vessel_id'])}
    for berth_id in (current.get('berth_id'),candidate.get('berth_id')):
        if not berth_id:
            continue
        referenced.add(('berth',berth_id))
        berth=by_id.get(('berth',berth_id))
        if berth:
            referenced.add(('port',berth['payload']['port_id']))
    for peer in related:
        referenced.add(('call',peer['call_id']))
        call=by_id.get(('call',peer['call_id']))
        if call:
            referenced.add(('vessel',call['payload']['vessel_id']))
            if call['payload'].get('berth_id'):
                referenced.add(('berth',call['payload']['berth_id']))
    return [{'id':c['id'],'kind':c['kind'],'record_id':c['record_id'],
             'fields':c['fields'],'detected_at':c['detected_at']}
            for c in unresolved
            if c['state']=='unresolved' and (c['kind'],c['record_id']) in referenced]


def analyze(records, call_id, candidate, original_conflicts=None, unresolved=None):
    by_id = {(record['kind'],record['record_id']):record for record in records}
    call = by_id[('call',call_id)]
    baseline = call['payload']
    projected = [{**r,'payload':candidate} if r['kind']=='call' and r['record_id']==call_id else r for r in records]
    original_conflicts = schedule_conflicts(records) if original_conflicts is None else original_conflicts
    old={key(c):c for c in original_conflicts if call_id in c['record_ids']}
    new={key(c):c for c in schedule_conflicts(projected) if call_id in c['record_ids']}
    related=[]
    for record in records:
        if record['kind']!='call' or record['record_id']==call_id or record['payload']['status'] in {'departed','cancelled'}:
            continue
        peer=record['payload']
        if not overlaps(candidate,peer) and not overlaps(baseline,peer):
            continue
        reasons=[]
        if candidate.get('berth_id') and candidate['berth_id']==peer['berth_id']: reasons.append('candidate_berth')
        if baseline.get('berth_id') and baseline['berth_id']==peer['berth_id']: reasons.append('baseline_berth')
        if candidate['vessel_id']==peer['vessel_id']: reasons.append('shared_vessel')
        if reasons:
            vessel=by_id.get(('vessel',peer['vessel_id']))
            related.append({'call_id':record['record_id'],'vessel_name':vessel['payload']['name'] if vessel else 'Unknown vessel',
                            'reasons':reasons,'source':record['source'],'known_at':record['known_at']})
    related.sort(key=lambda item:item['call_id'])
    disputes=relevant_source_disagreements(records,call_id,candidate,related,unresolved or [])
    ids={call_id}|{item['call_id'] for item in related}
    open_work=[{'kind':r['kind'],'record_id':r['record_id'],'call_id':r['payload']['call_id'],
                'status':r['payload']['status'],'source':r['source'],'known_at':r['known_at']}
               for r in records if r['kind'] in RELATED and r['payload'].get('call_id') in ids
               and r['payload'].get('status') not in CLOSED]
    open_work.sort(key=lambda item:(item['call_id'],item['kind'],item['record_id']))
    berth=by_id.get(('berth',candidate.get('berth_id'))) if candidate.get('berth_id') else None
    vessel=by_id.get(('vessel',candidate['vessel_id']))
    port=by_id.get(('port',berth['payload']['port_id'])) if berth else None
    missing=[]
    if not berth: missing.append('Berth assignment unavailable')
    if not vessel: missing.append('Vessel record unavailable')
    elif not berth or any(vessel['payload'].get(k) is None or berth['payload'].get('max_'+k) is None for k in ('length_m','draft_m')):
        missing.append('Recorded berth/vessel dimensional checks incomplete')
    if not port: missing.append('Port context unavailable')
    resources=[r for r in records if r['kind']=='resource' and port and r['payload']['port_id']==port['record_id']]
    unavailable=[{'record_id':r['record_id'],'name':r['payload']['name'],'resource_type':r['payload']['resource_type'],
                  'source':r['source'],'known_at':r['known_at']} for r in resources if not r['payload']['available']]
    if not resources: missing.append('No port resource availability recorded')
    else: missing.append('Resource-to-call allocation is unverified')
    return {
        'verification':'unresolved_source_disagreement' if disputes else 'recorded_conflict' if new else 'recorded_checks_clear_with_unknowns' if missing else 'recorded_checks_clear',
        'confidence':'uncalibrated',
        'introduced_conflicts':[new[k] for k in sorted(new.keys()-old.keys())],
        'cleared_conflicts':[old[k] for k in sorted(old.keys()-new.keys())],
        'related_calls':related,'open_work':open_work,'source_disagreements':disputes,'unavailable_port_resources':unavailable,
        'missing_checks':missing,'review_rank':None,
        'limitations':['No external AIS, weather, tide or navigational clearance is inferred.',
                       'Other calls are not rescheduled and no delay or monetary saving is predicted.',
                       'Port-wide resource availability does not establish allocation to this call.',
                       'Source completeness, freshness and conflicting external records require verification.'],
    }
