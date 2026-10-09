"""Evidence-bound coverage review of recorded calls.

This is a deterministic completeness/attention index, NOT a navigational safety,
berth clearance, vendor data freshness guarantee or forecast.
"""
from .product_coordination import schedule_conflicts

CLOSED = {'done', 'resolved', 'acknowledged', 'fulfilled', 'cancelled', 'declined', 'completed'}
ACTIVE_CALL = {'planned', 'arrived', 'berthed'}


def build_readiness(records, read_at):
    by_id = {(record['kind'], record['record_id']): record for record in records}
    conflicts = schedule_conflicts(records)
    call_conflicts = {}
    for conflict in conflicts:
        for call_id in conflict['record_ids']:
            call_conflicts.setdefault(call_id, []).append(conflict)

    reports = []
    for call in records:
        if call['kind'] != 'call' or call['payload'].get('status') not in ACTIVE_CALL:
            continue

        payload = call['payload']
        berth = by_id.get(('berth', payload.get('berth_id')))
        vessel = by_id.get(('vessel', payload.get('vessel_id')))
        port = by_id.get(('port', berth['payload'].get('port_id'))) if berth else None
        related = [r for r in records if r['payload'].get('call_id') == call['record_id']]
        checks = []

        def check(code, label, state, explanation, kind=None, record_id=None):
            checks.append({
                'code': code, 'label': label, 'state': state,
                'explanation': explanation, 'record_kind': kind,
                'record_id': record_id,
            })

        check('berth_assignment', 'Berth assignment',
              'recorded' if berth else 'missing',
              'Assigned to recorded berth ' + str(berth['payload']['name']) if berth
              else 'No assigned berth is recorded. Allocation remains unverified.',
              'berth' if berth else 'call', berth['record_id'] if berth else call['record_id'])

        geocoded = berth and berth['payload'].get('latitude') is not None and berth['payload'].get('longitude') is not None
        check('berth_geography', 'Geographic berth position',
              'recorded' if geocoded else 'missing',
              'Operator-provided berth coordinates are recorded; their survey accuracy is not independently verified.' if geocoded
              else 'Berth coordinates are absent; geographic placement cannot be inferred.',
              'berth' if berth else None, berth['record_id'] if berth else None)

        dimensions = ('length_m', 'draft_m')
        known = berth and vessel and all(
            berth['payload'].get('max_' + measure) is not None
            and vessel['payload'].get(measure) is not None for measure in dimensions)
        check('dimensional_limits', 'Recorded berth / vessel dimensions',
              'recorded' if known else 'missing',
              'Both length and draft values are recorded for vessel and berth; this is not navigational clearance.' if known
              else 'At least one vessel length/draft or berth maximum length/draft value is missing.',
              'berth' if berth else 'vessel', berth['record_id'] if berth else payload.get('vessel_id'))

        collision = call_conflicts.get(call['record_id'], [])
        check('schedule_conflicts', 'Recorded schedule constraints',
              'conflict' if collision else 'recorded',
              ' | '.join(item['explanation'] for item in collision) if collision
              else 'No overlap or dimensional violation found in recorded constraints only.',
              'call', call['record_id'])

        incidents = [r for r in related if r['kind'] == 'incident' and r['payload'].get('status') != 'resolved']
        check('open_incidents', 'Unresolved recorded incidents',
              'attention' if incidents else 'recorded',
              f'{len(incidents)} unresolved incident(s) require review.' if incidents else
              'No unresolved incident in this installation; unreported events cannot be excluded.',
              'incident' if incidents else None, incidents[0]['record_id'] if incidents else None)

        tasks = [r for r in related if r['kind'] == 'task' and r['payload'].get('status') != 'done']
        check('open_tasks', 'Unfinished recorded tasks',
              'attention' if tasks else 'recorded',
              f'{len(tasks)} recorded task(s) are unfinished.' if tasks else 'No unfinished task is recorded.',
              'task' if tasks else None, tasks[0]['record_id'] if tasks else None)

        threads = [r for r in related if r['kind'] in {'handoff', 'commitment', 'obligation'}
                   and r['payload'].get('status') not in CLOSED]
        check('coordination', 'Open coordination threads',
              'attention' if threads else 'recorded',
              f'{len(threads)} handoff / commitment / obligation thread(s) still open.' if threads
              else 'No open coordination thread is recorded; external acknowledgement is not inferred.',
              threads[0]['kind'] if threads else None, threads[0]['record_id'] if threads else None)

        port_resources = [r for r in records if r['kind'] == 'resource' and port and
                          r['payload'].get('port_id') == port['record_id']]
        unavailable = [r for r in port_resources if r['payload'].get('available') is False]
        check('port_resources', 'Port-wide resource picture',
              'attention' if unavailable else ('recorded' if port_resources else 'missing'),
              f'{len(unavailable)} port resource(s) recorded unavailable. Dependency on this call is not established.' if unavailable
              else f'{len(port_resources)} port resource(s) recorded; no specific call allocation is inferred.' if port_resources
              else 'No port resource availability is recorded; required resources are unknown.',
              'resource' if unavailable else None, unavailable[0]['record_id'] if unavailable else None)

        # Count only explicit resource links, never infer a required tug/pilot.
        assignments = [r for r in related if r['kind'] == 'resource_assignment'
                       and r['payload']['status'] in {'proposed','confirmed'}]
        confirmed = [r for r in assignments if r['payload']['status'] == 'confirmed']
        resource_lookup = {r['record_id']: r for r in port_resources}
        unavailable_assigned = [r for r in confirmed
                                 if not resource_lookup.get(r['payload']['resource_id']) or
                                 resource_lookup[r['payload']['resource_id']]['payload']['available'] is False]
        check('specific_resource_allocations', 'Specific resource-to-call allocations',
              'conflict' if unavailable_assigned else ('recorded' if confirmed else 'missing'),
              f'{len(unavailable_assigned)} confirmed call allocation(s) have missing/unavailable resources.' if unavailable_assigned
              else f'{len(confirmed)} confirmed, {len(assignments)-len(confirmed)} proposed allocation(s); recorded commitments, not independent provider acknowledgements.' if confirmed
              else 'No confirmed allocations for this call. Required resource types are not inferred.',
              'resource_assignment' if unavailable_assigned else None,
              unavailable_assigned[0]['record_id'] if unavailable_assigned else None)

        states = [item['state'] for item in checks]
        assessment = ('conflict' if 'conflict' in states else
                      'attention' if 'attention' in states else
                      'incomplete' if 'missing' in states else 'recorded')
        reports.append({
            'call_id': call['record_id'],
            'call_status': payload['status'],
            'vessel_name': vessel['payload']['name'] if vessel else 'Unidentified vessel',
            'berth_name': berth['payload']['name'] if berth else None,
            'eta': payload['eta'], 'etd': payload['etd'],
            'call_source': call['source'], 'known_at': call['known_at'],
            'assessment': assessment,
            'coverage': sum(item['state'] == 'recorded' for item in checks),
            'total_checks': len(checks),
            'checks': checks,
        })

    reports.sort(key=lambda call: (call['eta'], call['call_id']))
    return {
        'read_at': read_at,
        'scope': 'recorded_information_only',
        'summary': {
            'active_calls': len(reports),
            'conflicted_calls': sum(r['assessment'] == 'conflict' for r in reports),
            'attention_calls': sum(r['assessment'] == 'attention' for r in reports),
            'incomplete_calls': sum(r['assessment'] == 'incomplete' for r in reports),
            'fully_recorded_calls': sum(r['assessment'] == 'recorded' for r in reports),
        },
        'calls': reports,
    }
