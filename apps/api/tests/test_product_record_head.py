"""Edit conflicts must distinguish latest recorded revision from effective history."""
import pytest

from test_product import customer, activate, invite, write


@pytest.mark.parametrize('latest_time', ['2099-01-01T00:00:00Z', '2025-01-01T00:00:00Z'])
def test_head_exposes_write_revision_without_reinterpreting_effective_facts(customer, latest_time):
    first = write(customer, 'port', 'temporal-port', {'name': 'Effective port', 'timezone': 'UTC'},
                  valid_at='2026-01-01T00:00:00Z').json()
    latest = write(customer, 'port', 'temporal-port', {'name': 'Other effective time', 'timezone': 'UTC'},
                   revision=1, valid_at=latest_time).json()
    assert customer.get('/api/v1/workspace').json()['records'] == [first]
    before = customer.get('/api/v1/evidence').json()
    response = customer.get('/api/v1/records/port/temporal-port/head')
    assert response.status_code == 200, response.text
    assert response.json() == latest
    assert customer.get('/api/v1/workspace').json()['records'] == [first]
    assert customer.get('/api/v1/evidence').json() == before
    assert write(customer, 'port', 'temporal-port', {'name': 'Reviewed correction', 'timezone': 'UTC'},
                 revision=response.json()['revision']).status_code == 201
    assert len(customer.get('/api/v1/history').json()) == 3
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_record_head_requires_authentication(customer):
    customer.cookies.clear()
    assert customer.get('/api/v1/records/port/unknown/head').status_code == 401


@pytest.mark.parametrize('path', ['port/unknown', 'unknown/port'])
def test_unknown_record_head_returns_not_found(customer, path):
    assert customer.get(f'/api/v1/records/{path}/head').status_code == 404


def test_viewer_can_review_head_but_cannot_use_it_to_write(customer):
    write(customer, 'port', 'p', {'name': 'Port', 'timezone': 'UTC'})
    viewer = activate(customer.app, invite(customer, 'viewer'), 'viewer')
    response = viewer.get('/api/v1/records/port/p/head')
    assert response.status_code == 200, response.text
    assert write(viewer, 'port', 'p', {'name': 'Unauthorized', 'timezone': 'UTC'}, revision=1).status_code == 403


def test_reviewing_head_does_not_lock_or_bypass_a_newer_write(customer):
    write(customer, 'port', 'p', {'name': 'Port', 'timezone': 'UTC'})
    response = customer.get('/api/v1/records/port/p/head')
    assert response.status_code == 200, response.text
    assert write(customer, 'port', 'p', {'name': 'Concurrent update', 'timezone': 'UTC'}, revision=1).status_code == 201
    assert write(customer, 'port', 'p', {'name': 'Stale review', 'timezone': 'UTC'},
                 revision=response.json()['revision']).status_code == 409
