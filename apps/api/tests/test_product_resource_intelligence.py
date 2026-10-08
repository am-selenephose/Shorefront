"""Real source/assignment contracts and descriptive outcome metrics."""
from test_product import customer, headers, setup_call, write, invite, activate


def allocation(call_id='call-one',resource_id='tug-one',start='2026-10-05T09:30:00Z',
               end='2026-10-05T11:30:00Z',status='proposed',note=''):
    return {'call_id':call_id,'resource_id':resource_id,'starts_at':start,'ends_at':end,
            'status':status,'confirmation_note':note}


def test_assignment_enforces_same_port_identity_and_confirmed_overlap(customer):
    setup_call(customer)
    assert write(customer,'resource','tug-one',{'name':'Pilot tug A','port_id':'port-one','resource_type':'tug','available':True}).status_code==201
    assert write(customer,'vessel','vessel-two',{'name':'Second vessel'}).status_code==201
    assert write(customer,'call','call-two',{'vessel_id':'vessel-two','berth_id':'berth-one',
        'eta':'2026-10-05T10:00:00Z','etd':'2026-10-05T13:00:00Z'}).status_code==201

    missing=write(customer,'resource_assignment','a-missing',allocation(resource_id='missing'))
    assert missing.status_code==422
    assert write(customer,'port','second-port',{'name':'Other port','timezone':'UTC'}).status_code==201
    assert write(customer,'resource','foreign-tug',{'name':'Other port tug','port_id':'second-port',
        'resource_type':'tug','available':True}).status_code==201
    assert write(customer,'resource_assignment','a-cross',allocation(resource_id='foreign-tug')).status_code==422

    asserted=write(customer,'resource_assignment','a-one',allocation(status='confirmed'))
    assert asserted.status_code==422
    confirmed=write(customer,'resource_assignment','a-one',allocation(status='confirmed',note='Pilot desk approved tug A'))
    assert confirmed.status_code==201,confirmed.text
    assert write(customer,'resource_assignment','a-overlap',
        allocation(call_id='call-two',status='confirmed',note='Second desk')).status_code==409
    assert write(customer,'resource_assignment','a-next',
        allocation(call_id='call-two',start='2026-10-05T11:30:00Z',end='2026-10-05T12:00:00Z',
                   status='confirmed',note='Next duty')).status_code==201
    assert write(customer,'resource','tug-two',{'name':'Same port tug','port_id':'port-one',
        'resource_type':'tug','available':True}).status_code==201
    assert write(customer,'resource_assignment','a-one',
        {**allocation(resource_id='tug-two',status='released',note='Old assignment'), 'release_note':'Ended'},revision=1).status_code==409
    assert write(customer,'resource_assignment','a-one',
        {**allocation(status='released',note='Pilot desk approved tug A'),'release_note':'Duty ended'},revision=1).status_code==201
    assert write(customer,'resource_assignment','a-one',
        allocation(status='confirmed',note='Reopened'),revision=2).status_code==409
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_decision_detects_specific_assignments_and_rejects_unavailable_confirmed_resource(customer):
    setup_call(customer)
    assert write(customer,'resource','tug-one',{'name':'Tug one','port_id':'port-one','resource_type':'tug','available':True}).status_code==201
    assert write(customer,'resource_assignment','confirmed-slot',
        allocation(status='confirmed',note='Marine desk confirmation')).status_code==201
    packet=customer.post('/api/v1/decisions',headers=headers(customer),
                         json={'call_id':'call-one','question':'Allocate recorded berth'}).json()
    exact=packet['options'][0]['intelligence']
    assert exact['assigned_resources'][0]['resource_id']=='tug-one'
    assert exact['assigned_resources'][0]['status']=='confirmed'
    assert not exact['allocation_conflicts']
    assert not any('No explicit confirmed resource' in value for value in exact['missing_checks'])

    change=write(customer,'resource','tug-one',{'name':'Tug one','port_id':'port-one','resource_type':'tug','available':False},revision=1)
    assert change.status_code==201
    reassessed=customer.post('/api/v1/decisions',headers=headers(customer),
                             json={'call_id':'call-one','question':'Updated tug availability'}).json()
    assert reassessed['options'][0]['eligible'] is False
    assert any(item['kind']=='assigned_resource_unavailable' for item in reassessed['options'][0]['intelligence']['allocation_conflicts'])
    supervisor=activate(customer.app,invite(customer,'supervisor'),'supervisor')
    denied=supervisor.post('/api/v1/decisions/'+reassessed['id']+'/approve',
            headers=headers(supervisor),json={'option_id':'option-0','reason':'Cannot approve unavailable tug'})
    assert denied.status_code==422
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_measurements_refuse_to_infer_causal_savings_or_missing_outcomes(customer):
    setup_call(customer)
    empty=customer.get('/api/v1/decision-intelligence/outcomes')
    assert empty.status_code==200 and empty.json()['summary']['observation_coverage_pct'] is None
    packet=customer.post('/api/v1/decisions',headers=headers(customer),
                         json={'call_id':'call-one','question':'Observed later?'}).json()
    supervisor=activate(customer.app,invite(customer,'supervisor'),'supervisor')
    approved=supervisor.post('/api/v1/decisions/'+packet['id']+'/approve',
          headers=headers(supervisor),json={'option_id':'option-0','reason':'Approved plan'})
    assert approved.status_code==200,approved.text
    unobserved=customer.get('/api/v1/decision-intelligence/outcomes').json()
    assert unobserved['summary']['approved_decisions']==1
    assert unobserved['summary']['outcomes_missing']==1
    assert unobserved['summary']['mean_absolute_arrival_deviation_minutes'] is None
    assert write(customer,'outcome','observed-one',{'decision_id':packet['id'],
           'actual_arrival':'2026-10-05T10:18:00Z','actual_departure':'2026-10-05T15:24:00Z'}).status_code==201
    observed=customer.get('/api/v1/decision-intelligence/outcomes').json()
    assert observed['summary']['approved_decisions']==1
    assert observed['summary']['outcomes_recorded']==1
    assert observed['summary']['observation_coverage_pct']==100
    assert observed['summary']['mean_absolute_arrival_deviation_minutes']==18
    row=observed['measurements'][0]
    assert row['arrival_deviation_minutes']==18
    assert row['departure_deviation_minutes']==24
    assert row['occupancy_deviation_minutes']==6
    assert 'cash_saved' not in row and 'prediction_accuracy' not in observed['summary']
    assert any('not causal' in line for line in observed['limitations'])
    customer.cookies.clear()
    assert customer.get('/api/v1/decision-intelligence/outcomes').status_code==401


def test_scoped_external_feed_can_propose_allocation_but_not_forge_human_confirmation(customer):
    setup_call(customer)
    assert write(customer,'resource','tug-one',{'name':'Tug A','port_id':'port-one',
                 'resource_type':'tug','available':True}).status_code==201
    registered=customer.post('/api/v1/connections/sources',headers=headers(customer),
        json={'id':'port-dispatch','name':'Authorized port dispatch receipt','allowed_kinds':['resource_assignment'],
              'expires_in_hours':24})
    assert registered.status_code==201,registered.text
    token=registered.json()['token']
    body={'records':[{'kind':'resource_assignment','record_id':'allocation-feed',
        'expected_revision':0,'payload':allocation()}]}
    bearer={'Authorization':'Bearer '+token,'Idempotency-Key':'allocation-proposal-1'}
    proposed=customer.post('/api/v1/integrations/port-dispatch/records',headers=bearer,json=body)
    assert proposed.status_code==201,proposed.text
    assert proposed.json()['records'][0]['source']=='integration:port-dispatch'
    assert customer.get('/api/v1/connections/sources').json()[0]['last_used_at'] is not None
    # External machine bearer cannot convert a proposal to human-confirmed duty.
    forged={'records':[{'kind':'resource_assignment','record_id':'allocation-feed',
           'expected_revision':1,'payload':allocation(status='confirmed',note='Machine says approved')}]}
    forbidden=customer.post('/api/v1/integrations/port-dispatch/records',
                             headers={**bearer,'Idempotency-Key':'allocation-forgery'},json=forged)
    assert forbidden.status_code==403
    record=next(item for item in customer.get('/api/v1/workspace').json()['records']
                if item['record_id']=='allocation-feed')
    assert record['revision']==1 and record['payload']['status']=='proposed'
    confirmed=write(customer,'resource_assignment','allocation-feed',
                    allocation(status='confirmed',note='Human pilot desk confirmation'),revision=1)
    assert confirmed.status_code==201,confirmed.text
    revoke=customer.post('/api/v1/connections/sources/port-dispatch/revoke',headers=headers(customer),json={})
    assert revoke.status_code==200
    assert customer.post('/api/v1/integrations/port-dispatch/records',
                         headers={**bearer,'Idempotency-Key':'after-revoke'},json=body).status_code==401
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True
