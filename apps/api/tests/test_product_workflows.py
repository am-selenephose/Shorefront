"""Customer-visible coordination actions and the commands they authorize."""
from datetime import datetime

import pytest

from test_product import activate, customer, headers, invite, setup_call, write


def identity(client):
    return client.get('/api/v1/auth/me').json()['user']['id']


def desk(client):
    response = client.get('/api/v1/coordination')
    assert response.status_code == 200, response.text
    body = response.json()
    assert datetime.fromisoformat(body['read_at']).tzinfo is not None
    return {item['record']['record_id']: item for item in body['items']}


def statuses(item):
    return {action['status'] for action in item['actions']}


def coordination_body(recipient_id):
    return {'title': 'Arrival brief', 'call_id': 'call-one', 'recipient_id': recipient_id,
            'due_at': '2026-10-05T14:00:17.123456+05:00', 'note': 'Recorded arrival terms'}


def test_coordination_projection_requires_authentication(customer):
    customer.cookies.clear()
    assert customer.get('/api/v1/coordination').status_code == 401


def test_handoff_actions_follow_named_parties_and_preserve_complete_record(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    viewer = activate(customer.app, invite(customer, 'viewer'), 'viewer')
    body = coordination_body(identity(recipient))
    created = write(customer, 'handoff', 'brief', body).json()
    original_evidence = customer.get('/api/v1/evidence').json()
    item = desk(customer)['brief']
    assert item['record'] == created
    assert item['creator_id'] == identity(customer)
    assert item['actions'] == [{'status': 'sent', 'label': 'Send handoff',
                                'requires_proof': False, 'requires_review': False}]
    assert desk(recipient)['brief']['actions'] == []
    assert desk(viewer)['brief']['actions'] == []
    assert customer.get('/api/v1/evidence').json() == original_evidence

    sent = write(customer, 'handoff', 'brief', {**body, 'status': 'sent'}, revision=1).json()
    assert desk(customer)['brief']['actions'] == []
    action = desk(recipient)['brief']['actions'][0]
    assert action == {'status': 'acknowledged', 'label': 'Acknowledge handoff',
                      'requires_proof': True, 'requires_review': False}
    assert write(recipient, 'handoff', 'brief', {**sent['payload'], 'status': action['status']}, revision=2).status_code == 422
    acknowledged = {**sent['payload'], 'status': action['status'], 'proof': 'I received the arrival brief'}
    result = write(recipient, 'handoff', 'brief', acknowledged, revision=2, key='recipient-receipt')
    assert result.status_code == 201, result.text
    assert result.json()['payload']['due_at'] == created['payload']['due_at']
    assert write(recipient, 'handoff', 'brief', acknowledged, revision=2, key='recipient-receipt').json() == result.json()
    assert desk(recipient)['brief']['actions'] == []
    assert desk(customer)['brief']['creator_id'] == identity(customer)
    assert write(customer, 'handoff', 'brief', {**body, 'status': 'sent'}, revision=2).status_code == 409


def test_commitment_projection_gives_recipient_accept_decline_then_fulfillment(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    unrelated = activate(customer.app, invite(customer, 'supervisor'), 'supervisor')
    body = coordination_body(identity(recipient))
    assert write(customer, 'commitment', 'promise', body).status_code == 201
    assert statuses(desk(customer)['promise']) == {'cancelled'}
    assert statuses(desk(recipient)['promise']) == {'accepted', 'declined'}
    assert desk(unrelated)['promise']['actions'] == []
    accepted = {**body, 'status': 'accepted'}
    assert write(recipient, 'commitment', 'promise', accepted, revision=1).status_code == 201
    assert statuses(desk(recipient)['promise']) == {'fulfilled'}
    assert statuses(desk(customer)['promise']) == {'cancelled'}
    action = desk(recipient)['promise']['actions'][0]
    assert action['requires_proof'] is True
    assert write(recipient, 'commitment', 'promise', {**accepted, 'status': 'fulfilled',
                 'proof': 'Dispatcher receipt 42'}, revision=2).status_code == 201
    assert desk(recipient)['promise']['actions'] == []
    assert desk(customer)['promise']['actions'] == []


def test_obligation_projection_requires_review_and_documentary_completion(customer):
    setup_call(customer)
    assignee = activate(customer.app, invite(customer))
    body = {'title': 'Arrival notice', 'call_id': 'call-one', 'assignee_id': identity(assignee),
            'due_at': '2026-10-05T09:00:00Z', 'clause_reference': 'Customer SOP 4'}
    assert write(customer, 'obligation', 'notice', body).status_code == 201
    actions = {action['status']: action for action in desk(assignee)['notice']['actions']}
    assert set(actions) == {'active', 'cancelled'}
    assert actions['active']['requires_review'] is True
    assert actions['active']['requires_proof'] is False
    assert write(assignee, 'obligation', 'notice', {**body, 'status': 'active'}, revision=1).status_code == 422
    active = {**body, 'status': 'active', 'review_note': 'Checked against customer SOP 4'}
    assert write(assignee, 'obligation', 'notice', active, revision=1).status_code == 201
    actions = {action['status']: action for action in desk(assignee)['notice']['actions']}
    assert set(actions) == {'completed', 'cancelled'}
    assert actions['completed']['requires_proof'] is True
    assert actions['completed']['requires_review'] is True
    complete = {**active, 'status': 'completed', 'proof': 'Notice receipt 20'}
    assert write(assignee, 'obligation', 'notice', complete, revision=2).status_code == 201
    assert desk(assignee)['notice']['actions'] == []
    assert desk(customer)['notice']['actions'] == []


@pytest.mark.parametrize('kind', ['handoff', 'commitment', 'obligation'])
def test_coordination_cannot_assign_a_required_transition_to_a_viewer(customer, kind):
    setup_call(customer)
    viewer = activate(customer.app, invite(customer, 'viewer'), 'viewer')
    body = coordination_body(identity(viewer))
    if kind == 'obligation':
        body.pop('recipient_id')
        body.pop('note')
        body.update(assignee_id=identity(viewer), clause_reference='Customer SOP 4')
    result = write(customer, kind, 'reader-assignment', body)
    assert result.status_code == 422, result.text
    assert 'operational' in result.json()['detail'].lower()


def test_originator_can_cancel_existing_commitment_after_recipient_revocation(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    body = coordination_body(identity(recipient))
    assert write(customer, 'commitment', 'revoked-recipient', body).status_code == 201
    accepted = {**body, 'status': 'accepted'}
    assert write(recipient, 'commitment', 'revoked-recipient', accepted, revision=1).status_code == 201
    assert customer.post(f'/api/v1/team/{identity(recipient)}/revoke', headers=headers(customer)).status_code == 200
    assert recipient.get('/api/v1/coordination').status_code == 401
    result = write(customer, 'commitment', 'revoked-recipient', {**accepted, 'status': 'cancelled'}, revision=2)
    assert result.status_code == 201, result.text
    assert result.json()['payload']['recipient_id'] == body['recipient_id']
    assert desk(customer)['revoked-recipient']['actions'] == []
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True


def test_revoked_recipient_blocks_send_but_keeps_originator_cancellation_visible(customer):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    body = coordination_body(identity(recipient))
    assert write(customer, 'handoff', 'prepared', body).status_code == 201
    assert write(customer, 'commitment', 'proposed', body).status_code == 201
    assert customer.post(f'/api/v1/team/{identity(recipient)}/revoke', headers=headers(customer)).status_code == 200
    projected = desk(customer)
    assert projected['prepared']['actions'] == []
    assert statuses(projected['proposed']) == {'cancelled'}
    assert write(customer, 'handoff', 'prepared', {**body, 'status': 'sent'}, revision=1).status_code == 422


@pytest.mark.parametrize('kind, initial_status, target_status', [
    ('handoff', 'sent', 'acknowledged'), ('commitment', 'proposed', 'accepted')])
def test_fixed_due_date_accepts_identical_instant_without_accepting_changed_time(customer, kind, initial_status, target_status):
    setup_call(customer)
    recipient = activate(customer.app, invite(customer))
    body = coordination_body(identity(recipient))
    assert write(customer, kind, 'same-instant', body).status_code == 201
    revision = 1
    if initial_status == 'sent':
        assert write(customer, kind, 'same-instant', {**body, 'status': 'sent'}, revision=revision).status_code == 201
        revision += 1
    target = {**body, 'status': target_status, 'proof': 'Receipt confirmed', 'due_at': '2026-10-05T09:00:17.123456Z'}
    changed = write(recipient, kind, 'same-instant', {**target, 'due_at': '2026-10-05T09:00:00Z'}, revision=revision)
    assert changed.status_code == 409
    result = write(recipient, kind, 'same-instant', target, revision=revision)
    assert result.status_code == 201, result.text
    assert datetime.fromisoformat(result.json()['payload']['due_at']) == datetime.fromisoformat(body['due_at'])


@pytest.mark.parametrize('status', ['active', 'completed', 'cancelled'])
def test_active_obligation_cannot_rewrite_reviewed_terms_during_any_transition(customer, status):
    setup_call(customer)
    body = {'title': 'Arrival notice', 'call_id': 'call-one', 'assignee_id': identity(customer),
            'due_at': '2026-10-05T09:00:00Z', 'clause_reference': 'Customer SOP 4'}
    assert write(customer, 'obligation', 'reviewed', body).status_code == 201
    active = {**body, 'status': 'active', 'review_note': 'Checked customer SOP 4'}
    assert write(customer, 'obligation', 'reviewed', active, revision=1).status_code == 201
    result = write(customer, 'obligation', 'reviewed', {**active, 'status': status,
                   'clause_reference': 'Different unreviewed SOP 8', 'proof': 'Receipt 20'}, revision=2)
    assert result.status_code == 409, result.text
    corrected_review = {**active, 'status': status, 'review_note': 'Corrected review citation for SOP 4', 'proof': 'Receipt 20'}
    assert write(customer, 'obligation', 'reviewed', corrected_review, revision=2).status_code == 201
    assert customer.get('/api/v1/evidence').json()['audit_valid'] is True
