"""What-if port planning stays advisory and cannot alter the durable schedule."""
from test_product import customer, headers, setup_call, write


def test_what_if_needs_login_and_csrf(customer):
    setup_call(customer)
    draft={'call_id':'call-one','berth_id':'berth-one',
           'eta':'2026-10-05T10:00:00Z','etd':'2026-10-05T15:00:00Z'}
    assert customer.post('/api/v1/plan/what-if', json=draft).status_code == 403
    customer.cookies.clear()
    assert customer.post('/api/v1/plan/what-if',json=draft,headers={'Origin':'https://shorefront.test'}).status_code in {401,403}


def test_what_if_compares_conflicts_but_never_modifies_record(customer):
    setup_call(customer)
    assert write(customer,'berth','second-berth',{'name':'East Berth','port_id':'port-one','max_length_m':300}).status_code == 201
    assert write(customer,'vessel','second-vessel',{'name':'MV Secondary','length_m':150}).status_code == 201
    assert write(customer,'call','second-call',{'vessel_id':'second-vessel','berth_id':'second-berth',
        'eta':'2026-10-05T11:00:00Z','etd':'2026-10-05T16:00:00Z'}).status_code == 201
    before = customer.get('/api/v1/workspace').json()['records']
    request={'call_id':'call-one','berth_id':'second-berth',
             'eta':'2026-10-05T12:00:00Z','etd':'2026-10-05T14:00:00Z'}
    response=customer.post('/api/v1/plan/what-if',json=request,headers=headers(customer))
    assert response.status_code == 200,response.text
    preview=response.json()
    assert preview['baseline']['conflicts']==[]
    assert any(c['kind']=='berth_overlap' for c in preview['candidate']['conflicts'])
    assert preview['candidate']['berth_name']=='East Berth'
    assert preview['change']['eta_minutes']==120
    assert preview['change']['etd_minutes']==-60
    assert preview['read_only'] is True
    assert customer.get('/api/v1/workspace').json()['records']==before
    assert customer.post('/api/v1/plan/what-if',json={**request,'berth_id':'unregistered'},headers=headers(customer)).status_code == 422
    assert customer.post('/api/v1/plan/what-if',json={**request,'etd':'2026-10-05T10:00:00Z'},headers=headers(customer)).status_code == 422
    assert customer.get('/api/v1/workspace').json()['records']==before

    assert write(customer, 'port','elsewhere',{'name':'Different Port','timezone':'UTC'}).status_code == 201
    assert write(customer, 'berth','different-port-berth',{'name':'Another City Berth','port_id':'elsewhere'}).status_code == 201
    cross_port=customer.post('/api/v1/plan/what-if',json={**request,'berth_id':'different-port-berth'},headers=headers(customer))
    assert cross_port.status_code == 422
    assert 'different port' in cross_port.text.lower()
