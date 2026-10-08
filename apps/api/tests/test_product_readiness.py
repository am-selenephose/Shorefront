"""Verified call coverage: no invented safety or provider observations."""
from datetime import datetime, timezone

from test_product import customer, headers, setup_call, write


def test_readiness_requires_auth_and_starts_empty(customer):
    assert customer.get('/api/v1/readiness').json()['calls'] == []
    customer.cookies.clear()
    assert customer.get('/api/v1/readiness').status_code == 401


def test_readiness_surfaces_unknown_berth_particulars_and_open_incident(customer):
    setup_call(customer)
    response = customer.get('/api/v1/readiness')
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['summary']['active_calls'] == 1
    call = report['calls'][0]
    assert call['call_id'] == 'call-one'
    checks = {row['code']: row for row in call['checks']}
    assert checks['berth_assignment']['state'] == 'recorded'
    assert checks['berth_geography']['state'] == 'missing'
    assert checks['dimensional_limits']['state'] == 'missing'
    assert call['call_source'] == 'operator entry'
    assert call['assessment'] == 'incomplete'
    assert write(customer, 'incident', 'incident-one', {
        'call_id': 'call-one', 'title': 'Tug failure', 'severity': 'critical'
    }).status_code == 201
    blocked = customer.get('/api/v1/readiness').json()['calls'][0]
    assert blocked['assessment'] == 'attention'
    assert any(check['code'] == 'open_incidents' and check['state'] == 'attention' for check in blocked['checks'])


def test_readiness_conflicts_are_recorded_not_traffic_predictions(customer):
    setup_call(customer)
    assert write(customer, 'vessel', 'vessel-two', {'name':'Next Vessel', 'length_m': 200}).status_code == 201
    assert write(customer, 'call', 'call-two', {
        'vessel_id': 'vessel-two','berth_id':'berth-one',
        'eta':'2026-10-05T11:00:00Z','etd':'2026-10-05T14:00:00Z'
    }).status_code == 201
    report = customer.get('/api/v1/readiness').json()
    assert report['summary']['conflicted_calls'] == 2
    assert all(call['assessment'] == 'conflict' for call in report['calls'])
    assert all(any(check['code'] == 'schedule_conflicts' and check['state'] == 'conflict'
                   for check in call['checks']) for call in report['calls'])
