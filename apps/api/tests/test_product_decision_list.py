"""Decision navigation must remain complete, authenticated and read-only."""
import pytest

from test_product import customer, setup_call, headers, invite, activate


def propose(client, question):
    response = client.post('/api/v1/decisions', headers=headers(client), json={'call_id':'call-one', 'question':question})
    assert response.status_code == 201, response.text
    return response.json()


def test_paging_reaches_more_than_one_hundred_packets_without_duplicates(customer):
    setup_call(customer)
    expected = sorted(propose(customer, f'Review {index}')['id'] for index in range(103))
    before = customer.get('/api/v1/evidence').json()
    seen = []
    after = ''
    for _ in range(5):
        response = customer.get('/api/v1/decisions', params={'limit':25, 'after':after})
        assert response.status_code == 200
        ids = [row['id'] for row in response.json()]
        seen.extend(ids)
        after = ids[-1]
    assert seen == expected
    assert customer.get('/api/v1/decisions', params={'after':after}).json() == []
    assert customer.get('/api/v1/evidence').json() == before


def test_search_is_literal_and_filters_before_limit(customer):
    setup_call(customer)
    items = [propose(customer, question) for question in ['Normal plan', 'Berth 100%_ready / today', 'bErTh 100XXready / today']]
    wanted = items[1]
    assert [r['id'] for r in customer.get('/api/v1/decisions', params={'q':'  BERTH 100%_  ', 'limit':1}).json()] == [wanted['id']]
    assert [r['id'] for r in customer.get('/api/v1/decisions', params={'q':wanted['id']}).json()] == [wanted['id']]
    assert len(customer.get('/api/v1/decisions', params={'q':'call-one'}).json()) == 3
    assert customer.get('/api/v1/decisions', params={'q':'absent'}).json() == []


def test_pending_approved_filter_does_not_change_receipts_or_viewer_authority(customer):
    setup_call(customer)
    approved = propose(customer, 'Approve this recorded plan')
    pending = propose(customer, 'Leave this packet pending')
    supervisor = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    response = supervisor.post(f"/api/v1/decisions/{approved['id']}/approve", headers=headers(supervisor),
                               json={'option_id':'option-0','reason':'Human review'})
    assert response.status_code == 200, response.text
    viewer = activate(customer.app, invite(customer, 'viewer'), 'viewer')
    before = customer.get('/api/v1/evidence').json()
    assert [r['id'] for r in viewer.get('/api/v1/decisions', params={'state':'pending'}).json()] == [pending['id']]
    assert [r['id'] for r in viewer.get('/api/v1/decisions', params={'state':'approved'}).json()] == [approved['id']]
    assert customer.get('/api/v1/evidence').json() == before
    customer.cookies.clear()
    assert customer.get('/api/v1/decisions', params={'q':'call-one','state':'pending'}).status_code == 401


@pytest.mark.parametrize('params', [{'limit':0}, {'limit':501}, {'after':'x'*97}, {'q':'x'*201}, {'state':'unknown'}])
def test_invalid_history_query_rejected(customer, params):
    assert customer.get('/api/v1/decisions', params=params).status_code == 422
