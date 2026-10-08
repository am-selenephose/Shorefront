"""Impact review is evidence-bound and never silently changes a port schedule."""
from test_product import customer, headers, setup_call, write


def create_packet(client):
    result=client.post('/api/v1/decisions', headers=headers(client),
                       json={'call_id':'call-one','question':'Which recorded berth window should be reviewed?'})
    assert result.status_code==201, result.text
    return result.json()


def test_packet_contains_explainable_impact_and_does_not_mutate_workspace(customer):
    setup_call(customer)
    assert write(customer,'berth','east',{'name':'East Berth','port_id':'port-one','max_length_m':300}).status_code==201
    assert write(customer,'vessel','secondary',{'name':'Second Vessel','length_m':160}).status_code==201
    assert write(customer,'call','secondary-call',{'vessel_id':'secondary','berth_id':'berth-one',
          'eta':'2026-10-05T11:00:00Z','etd':'2026-10-05T13:00:00Z'}).status_code==201
    assert write(customer,'task','linked-task',{'title':'Verify planned call','call_id':'call-one',
          'due_at':'2026-10-05T09:30:00Z','status':'open'}).status_code==201
    assert write(customer,'resource','unavailable-tug',{'name':'Tug unavailable','port_id':'port-one',
          'resource_type':'tug','available':False}).status_code==201
    before=customer.get('/api/v1/workspace').json()['records']
    packet=create_packet(customer)
    baseline=packet['options'][0]
    assert baseline['eligible'] is False
    assert baseline['intelligence']['verification']=='recorded_conflict'
    assert any(item['call_id']=='secondary-call' for item in baseline['intelligence']['related_calls'])
    assert any(item['record_id']=='linked-task' for item in baseline['intelligence']['open_work'])
    assert baseline['intelligence']['unavailable_port_resources'][0]['name']=='Tug unavailable'
    assert baseline['intelligence']['confidence']=='uncalibrated'
    assert baseline['intelligence']['review_rank'] is None
    assert all('predicted_delay' not in option['intelligence'] for option in packet['options'])

    alternatives=[option for option in packet['options'] if option['eligible']]
    assert alternatives, packet['options']
    assert any(item['cleared_conflicts'] for item in [option['intelligence'] for option in alternatives])
    assert sorted(option['intelligence']['review_rank'] for option in alternatives)==list(range(1,len(alternatives)+1))
    assert customer.get('/api/v1/workspace').json()['records']==before
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_packet_rejects_stale_or_modified_sources(customer):
    setup_call(customer)
    packet=create_packet(customer)
    before=customer.get('/api/v1/workspace').json()['records']
    assert packet['options'][0]['intelligence']['missing_checks']
    assert 'not' in packet['options'][0]['intelligence']['limitations'][0].lower() or packet['options'][0]['intelligence']['limitations']
    assert write(customer,'resource','new-tug',{'name':'Available tug','port_id':'port-one',
          'resource_type':'tug','available':True}).status_code==201
    # The old evidence packet remains frozen and can no longer be approved.
    from test_product import invite, activate
    supervisor=activate(customer.app,invite(customer,'supervisor'),'supervisor')
    response=supervisor.post('/api/v1/decisions/'+packet['id']+'/approve',headers=headers(supervisor),
                             json={'option_id':'option-0','reason':'Reviewed, despite new facts'})
    assert response.status_code==409
    assert customer.get('/api/v1/workspace').json()['records'] != before
    assert customer.get('/api/v1/decisions/'+packet['id']).json()['receipt'] is None


def test_exact_what_if_becomes_human_reviewed_packet_not_automatic_schedule_change(customer):
    from test_product import activate, invite
    setup_call(customer)
    assert write(customer,'berth','east',{'name':'East Quay','port_id':'port-one','max_length_m':400}).status_code==201
    scenario={'call_id':'call-one','berth_id':'east',
              'eta':'2026-10-05T12:00:00Z','etd':'2026-10-05T17:00:00Z'}
    simulation=customer.post('/api/v1/plan/what-if',headers=headers(customer),json=scenario)
    assert simulation.status_code==200,simulation.text
    before=customer.get('/api/v1/workspace').json()['records']
    assert simulation.json()['impact']['confidence']=='uncalibrated'
    assert simulation.json()['candidate']['conflicts']==[]
    packet=customer.post('/api/v1/decisions',headers=headers(customer),
                         json={'call_id':'call-one','question':'Review exact simulated plan',
                               'proposed':{k:v for k,v in scenario.items() if k!='call_id'}})
    assert packet.status_code==201,packet.text
    frozen=packet.json()
    exact=next(o for o in frozen['options'] if o['label'].startswith('Operator-proposed'))
    assert exact['eligible'] is True
    assert exact['call_payload']['berth_id']=='east'
    assert exact['call_payload']['eta'].startswith('2026-10-05T12:00:00')
    assert exact['intelligence']['review_rank'] is not None
    assert customer.get('/api/v1/workspace').json()['records']==before

    supervisor=activate(customer.app,invite(customer,'supervisor'),'supervisor')
    approved=supervisor.post('/api/v1/decisions/'+frozen['id']+'/approve',
                            headers=headers(supervisor),
                            json={'option_id':exact['id'],'reason':'Reviewed schedule and source constraints'})
    assert approved.status_code==200,approved.text
    updated=next(r for r in customer.get('/api/v1/workspace').json()['records']
                 if r['kind']=='call' and r['record_id']=='call-one')
    assert updated['payload']['berth_id']=='east'
    assert updated['payload']['eta'].startswith('2026-10-05T12:00:00')
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_operator_proposal_rejects_unregistered_berth_and_cross_port(customer):
    setup_call(customer)
    proposal={'call_id':'call-one','question':'Review proposed berth',
              'proposed':{'berth_id':'missing','eta':'2026-10-05T10:00:00Z',
                          'etd':'2026-10-05T15:00:00Z'}}
    failed=customer.post('/api/v1/decisions',headers=headers(customer),json=proposal)
    assert failed.status_code==422
    assert write(customer,'port','port-two',{'name':'Other Port','timezone':'UTC'}).status_code==201
    assert write(customer,'berth','other-berth',{'name':'Other Berth','port_id':'port-two'}).status_code==201
    proposal['proposed']['berth_id']='other-berth'
    assert customer.post('/api/v1/decisions',headers=headers(customer),json=proposal).status_code==422
    assert customer.get('/api/v1/decisions').json()==[]
