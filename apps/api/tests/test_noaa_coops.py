import pytest
from datetime import datetime, timedelta, timezone

from test_product import customer, headers, write, build_app, bootstrap, ORIGIN
from fastapi.testclient import TestClient


def test_disabled_noaa_port_context_is_explicit_and_requires_login(customer):
    assert write(customer, 'port', 'port-noaa', {
        'name':'San Francisco Port', 'timezone':'America/Los_Angeles',
        'noaa_station_id':'9414290',
    }).status_code==201
    response=customer.get('/api/v1/environment/noaa?port_id=port-noaa')
    assert response.status_code==200
    assert response.json()['status']=='disabled'
    assert response.json()['observation'] is None
    customer.cookies.clear()
    assert customer.get('/api/v1/environment/noaa?port_id=port-noaa').status_code==401


def test_enabled_noaa_context_is_bounded_to_configured_port(tmp_path, monkeypatch):
    seen=[]
    monkeypatch.setenv('SHOREFRONT_NOAA_ENABLED','1')
    observation={
        'provider':'NOAA CO-OPS','station_id':'9414290',
        'status':'current',
        'observation':{'level_m':1.23,'observed_at':'2026-10-08T12:00:00+00:00','datum':'MLLW','units':'m','quality':'preliminary'},
        'source_url':'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter',
        'retrieved_at':'2026-10-08T12:08:00+00:00',
        'limitations':['Not navigational clearance'],
    }
    def reader(station):
        seen.append(station)
        return observation

    with TestClient(build_app(tmp_path/'noaa.db', noaa_reader=reader), base_url=ORIGIN) as client:
        bootstrap(client)
        assert client.get('/api/v1/environment/noaa?port_id=unknown').status_code==404
        assert write(client,'port','local-port',{'name':'Local','timezone':'UTC'}).status_code==201
        absent=client.get('/api/v1/environment/noaa?port_id=local-port')
        assert absent.status_code==200
        assert absent.json()['status']=='not_configured'
        assert seen==[]
        assert write(client,'port','noaa-port',{'name':'US Station','timezone':'UTC',
                      'noaa_station_id':'9414290'}).status_code==201
        response=client.get('/api/v1/environment/noaa?port_id=noaa-port')
        assert response.status_code==200,response.text
        assert response.json()['observation']['level_m']==1.23
        assert response.json()['physical_execution_authorized'] is False
        assert response.json()['scope']=='operator_configured_station'
        assert seen==['9414290']


def test_noaa_client_validates_station_source_freshness_and_handles_outage():
    from shorefront_api.noaa_coops import NoaaCoopsClient
    now=datetime(2026,10,8,12,8,tzinfo=timezone.utc)
    class Reply:
        def __init__(self,data): self.data=data
        def read(self,n): return self.data
        def __enter__(self): return self
        def __exit__(self,*args): pass
    import json
    requests=[]
    def opener(url,timeout):
        requests.append((url,timeout))
        return Reply(json.dumps({
            'metadata':{'id':'9414290','name':'San Francisco'},
            'data':[{'t':'2026-10-08 12:00','v':'1.230','q':'p','f':'0,0,0,0'}],
        }).encode())
    client=NoaaCoopsClient(now=lambda:now,opener=opener)
    current=client.read('9414290')
    assert current['status']=='current'
    assert current['observation']['level_m']==1.23
    assert current['observation']['datum']=='MLLW'
    assert current['observation']['quality']=='preliminary'
    assert requests[0][1]<=5
    assert requests[0][0].startswith('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?')
    assert 'station=9414290' in requests[0][0]
    assert client.read('9414290')['status']=='current'
    assert len(requests)==1

    late=NoaaCoopsClient(now=lambda:now+timedelta(hours=1),opener=opener)
    assert late.read('9414290')['status']=='stale'
    invalid=NoaaCoopsClient(now=lambda:now,opener=lambda url,timeout:Reply(b'{"Error":"not found"}'))
    assert invalid.read('9414290')['status']=='unavailable'
    offline=NoaaCoopsClient(now=lambda:now,opener=lambda url,timeout: (_ for _ in ()).throw(OSError('offline')))
    assert offline.read('9414290')['status']=='unavailable'
    assert offline.read('invalid!')['status']=='unavailable'

@pytest.mark.parametrize('returned', [
    None,
    'invalid source',
    {},
    {'station_id':'9414290','status':'imaginary','physical_execution_authorized':False},
    {'station_id':'9414750','status':'current','physical_execution_authorized':False},
    {'provider':'NOAA CO-OPS','station_id':'9414290','status':'current',
     'observation':{'level_m':float('nan'),'observed_at':'2026-10-08T12:00:00+00:00',
                    'datum':'MLLW','units':'m','quality':'preliminary'}},
])
def test_malformed_noaa_provider_cannot_surface_as_trusted_context(tmp_path,monkeypatch,returned):
    monkeypatch.setenv('SHOREFRONT_NOAA_ENABLED','1')
    with TestClient(build_app(tmp_path/'fail-closed.db',noaa_reader=lambda station:returned),base_url=ORIGIN) as client:
        bootstrap(client)
        assert write(client,'port','safe-port',{'name':'US','timezone':'UTC','noaa_station_id':'9414290'}).status_code==201
        result=client.get('/api/v1/environment/noaa?port_id=safe-port')
        assert result.status_code==200
        assert result.json()['status']=='unavailable'
        assert result.json()['observation'] is None
        assert result.json()['physical_execution_authorized'] is False


def test_noaa_client_bad_json_shape_is_unavailable_not_server_error():
    from shorefront_api.noaa_coops import NoaaCoopsClient
    class Reply:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,n): return b'[]'
    result=NoaaCoopsClient(opener=lambda url,timeout:Reply()).read('9414290')
    assert result['status']=='unavailable'
    assert result['observation'] is None
