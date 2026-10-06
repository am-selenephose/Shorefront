"""Scoped machine ingestion and partner projections for the operational workspace."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import insert, select, update

from .product_models import IntegrationBatch, PartnerGrantCreate, RecordCommand, SourceCreate, now, stamp
from .product_store import (canonical, commands, connection_sources, digest, partner_grants)


def _expires(hours: int) -> str:
    return stamp(now() + timedelta(hours=hours))


def _expired(value: str) -> bool:
    return datetime.fromisoformat(value).astimezone(timezone.utc) <= now()


def _bearer(request: Request) -> str:
    value = request.headers.get('authorization', '')
    if not value.startswith('Bearer ') or not value[7:].strip() or len(value) > 300:
        raise HTTPException(401, 'A valid connection bearer token is required')
    return value[7:].strip()


def _source_public(row) -> dict:
    return {
        'id': row['id'],
        'name': row['name'],
        'allowed_kinds': json.loads(row['allowed_kinds']),
        'active': bool(row['active']),
        'created_by': row['created_by'],
        'created_at': row['created_at'],
        'expires_at': row['expires_at'],
        'expired': _expired(row['expires_at']),
        'last_used_at': row['last_used_at'],
        'write_count': row['write_count'],
    }


def _grant_public(row) -> dict:
    return {
        'id': row['id'],
        'name': row['name'],
        'allowed_kinds': json.loads(row['allowed_kinds']),
        'fields': json.loads(row['field_rules']),
        'call_ids': json.loads(row['call_ids']),
        'active': bool(row['active']),
        'created_by': row['created_by'],
        'created_at': row['created_at'],
        'expires_at': row['expires_at'],
        'expired': _expired(row['expires_at']),
        'last_used_at': row['last_used_at'],
        'access_count': row['access_count'],
    }


def create_source(store, connection, actor, body: SourceCreate) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    if connection.execute(select(connection_sources.c.id).where(connection_sources.c.id == body.id)).scalar_one_or_none():
        raise HTTPException(409, 'Connection source already exists')
    token = secrets.token_urlsafe(32)
    created = stamp(now())
    row = {
        'id': body.id,
        'name': body.name,
        'digest': digest(token),
        'allowed_kinds': canonical(body.allowed_kinds),
        'active': 1,
        'created_by': actor['id'],
        'created_at': created,
        'expires_at': _expires(body.expires_in_hours),
        'last_used_at': None,
        'write_count': 0,
    }
    connection.execute(insert(connection_sources).values(**row))
    store.add_audit(connection, actor['id'], 'connection.source.created',
                    {'id': body.id, 'name': body.name, 'allowed_kinds': body.allowed_kinds,
                     'expires_at': row['expires_at']})
    return {'source': _source_public(row), 'token': token}


def list_sources(connection, actor) -> list[dict]:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    rows = connection.execute(select(connection_sources).order_by(connection_sources.c.id)).mappings()
    return [_source_public(row) for row in rows]


def revoke_source(store, connection, actor, source_id: str) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    row = connection.execute(select(connection_sources).where(connection_sources.c.id == source_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Connection source not found')
    if row['active']:
        connection.execute(update(connection_sources).where(connection_sources.c.id == source_id).values(active=0))
        store.add_audit(connection, actor['id'], 'connection.source.revoked', {'id': source_id})
    return {**_source_public({**row, 'active': 0}), 'active': False}


def rotate_source(store, connection, actor, source_id: str, hours: int) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    row = connection.execute(select(connection_sources).where(connection_sources.c.id == source_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Connection source not found')
    token = secrets.token_urlsafe(32)
    expires_at = _expires(hours)
    connection.execute(update(connection_sources).where(connection_sources.c.id == source_id).values(
        digest=digest(token), active=1, expires_at=expires_at))
    refreshed = {**row, 'digest': digest(token), 'active': 1, 'expires_at': expires_at}
    store.add_audit(connection, actor['id'], 'connection.source.rotated',
                    {'id': source_id, 'expires_at': expires_at})
    return {'source': _source_public(refreshed), 'token': token}


def _authenticated_source(connection, request: Request, source_id: str):
    token = _bearer(request)
    row = connection.execute(select(connection_sources).where(
        connection_sources.c.id == source_id,
        connection_sources.c.digest == digest(token),
    )).mappings().first()
    if not row or not row['active'] or _expired(row['expires_at']):
        raise HTTPException(401, 'Connection credential is invalid, expired or revoked')
    return row


def ingest_records(store, connection, request: Request, source_id: str, body: IntegrationBatch, key: str):
    row = _authenticated_source(connection, request, source_id)
    allowed = set(json.loads(row['allowed_kinds']))
    forbidden = sorted({item.kind for item in body.records} - allowed)
    if forbidden:
        raise HTTPException(403, f'Connection is not allowed to write: {", ".join(forbidden)}')
    actor = {'id': f'integration:{source_id}', 'role': 'operator', 'active': 1}
    intent = digest(canonical({'source_id': source_id, 'records': body.model_dump(mode='json')}))
    prior = connection.execute(select(commands).where(
        commands.c.actor_id == actor['id'], commands.c.key == key)).mappings().first()
    if prior:
        if prior['digest'] != intent:
            raise HTTPException(409, 'Idempotency key already belongs to another integration command')
        return json.loads(prior['response'])
    results = []
    for index, item in enumerate(body.records):
        command = RecordCommand(
            record_id=item.record_id,
            expected_revision=item.expected_revision,
            valid_at=item.valid_at,
            source=f'integration:{source_id}',
            payload=item.payload,
        )
        results.append(store.write_record(connection, actor, item.kind, command,
                                          digest(f'integration:{source_id}:{key}:{index}')))
    response = {'records': results}
    connection.execute(insert(commands).values(actor_id=actor['id'], key=key,
                                               digest=intent, response=canonical(response)))
    connection.execute(update(connection_sources).where(connection_sources.c.id == source_id).values(
        last_used_at=stamp(now()), write_count=connection_sources.c.write_count + len(results)))
    return response


def create_partner_grant(store, connection, actor, body: PartnerGrantCreate) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    if connection.execute(select(partner_grants.c.id).where(partner_grants.c.id == body.id)).scalar_one_or_none():
        raise HTTPException(409, 'Partner projection grant already exists')
    # Call scopes are validated at grant creation so a typo never broadens to an unscoped projection.
    if body.call_ids:
        effective = {(record['kind'], record['record_id']) for record in store.snapshot(connection)}
        missing = [call_id for call_id in body.call_ids if ('call', call_id) not in effective]
        if missing:
            raise HTTPException(422, f'Unknown effective call scope: {", ".join(missing)}')
    token = secrets.token_urlsafe(32)
    row = {
        'id': body.id,
        'name': body.name,
        'digest': digest(token),
        'allowed_kinds': canonical(body.allowed_kinds),
        'field_rules': canonical(body.fields),
        'call_ids': canonical(body.call_ids),
        'active': 1,
        'created_by': actor['id'],
        'created_at': stamp(now()),
        'expires_at': _expires(body.expires_in_hours),
        'last_used_at': None,
        'access_count': 0,
    }
    connection.execute(insert(partner_grants).values(**row))
    store.add_audit(connection, actor['id'], 'connection.partner_grant.created',
                    {'id': body.id, 'name': body.name, 'allowed_kinds': body.allowed_kinds,
                     'call_ids': body.call_ids, 'expires_at': row['expires_at']})
    return {'grant': _grant_public(row), 'token': token}


def list_partner_grants(connection, actor) -> list[dict]:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    rows = connection.execute(select(partner_grants).order_by(partner_grants.c.id)).mappings()
    return [_grant_public(row) for row in rows]


def revoke_partner_grant(store, connection, actor, grant_id: str) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    row = connection.execute(select(partner_grants).where(partner_grants.c.id == grant_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Partner projection grant not found')
    if row['active']:
        connection.execute(update(partner_grants).where(partner_grants.c.id == grant_id).values(active=0))
        store.add_audit(connection, actor['id'], 'connection.partner_grant.revoked', {'id': grant_id})
    return {**_grant_public({**row, 'active': 0}), 'active': False}


def rotate_partner_grant(store, connection, actor, grant_id: str, hours: int) -> dict:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    row = connection.execute(select(partner_grants).where(partner_grants.c.id == grant_id)).mappings().first()
    if not row:
        raise HTTPException(404, 'Partner projection grant not found')
    token = secrets.token_urlsafe(32)
    expires_at = _expires(hours)
    connection.execute(update(partner_grants).where(partner_grants.c.id == grant_id).values(
        digest=digest(token), active=1, expires_at=expires_at))
    refreshed = {**row, 'digest': digest(token), 'active': 1, 'expires_at': expires_at}
    store.add_audit(connection, actor['id'], 'connection.partner_grant.rotated',
                    {'id': grant_id, 'expires_at': expires_at})
    return {'grant': _grant_public(refreshed), 'token': token}


def _authenticated_grant(connection, request: Request):
    token = _bearer(request)
    row = connection.execute(select(partner_grants).where(partner_grants.c.digest == digest(token))).mappings().first()
    if not row or not row['active'] or _expired(row['expires_at']):
        raise HTTPException(401, 'Partner projection credential is invalid, expired or revoked')
    return row


def _call_scope(records: list[dict], call_ids: list[str]) -> set[tuple[str, str]]:
    if not call_ids:
        return {(record['kind'], record['record_id']) for record in records}
    by_key = {(record['kind'], record['record_id']): record for record in records}
    keep = {('call', call_id) for call_id in call_ids}
    vessel_ids, berth_ids, incident_ids, port_ids = set(), set(), set(), set()
    for call_id in call_ids:
        call = by_key.get(('call', call_id))
        if not call:
            continue
        if call['payload'].get('vessel_id'):
            vessel_ids.add(call['payload']['vessel_id'])
        if call['payload'].get('berth_id'):
            berth_ids.add(call['payload']['berth_id'])
    keep |= {('vessel', value) for value in vessel_ids}
    keep |= {('berth', value) for value in berth_ids}
    for berth_id in berth_ids:
        berth = by_key.get(('berth', berth_id))
        if berth and berth['payload'].get('port_id'):
            port_ids.add(berth['payload']['port_id'])
    keep |= {('port', value) for value in port_ids}
    for record in records:
        if record['payload'].get('call_id') in call_ids:
            keep.add((record['kind'], record['record_id']))
            if record['kind'] == 'incident':
                incident_ids.add(record['record_id'])
    for record in records:
        if record['kind'] == 'task' and record['payload'].get('incident_id') in incident_ids:
            keep.add(('task', record['record_id']))
        if record['kind'] == 'resource' and record['payload'].get('port_id') in port_ids:
            keep.add(('resource', record['record_id']))
    return keep


def partner_projection(store, connection, request: Request) -> dict:
    row = _authenticated_grant(connection, request)
    allowed = set(json.loads(row['allowed_kinds']))
    fields = json.loads(row['field_rules'])
    call_ids = json.loads(row['call_ids'])
    records = store.snapshot(connection)
    scope = _call_scope(records, call_ids)
    projected = []
    for record in records:
        key = (record['kind'], record['record_id'])
        if record['kind'] not in allowed or key not in scope:
            continue
        permitted = fields[record['kind']]
        projected.append({
            'kind': record['kind'],
            'record_id': record['record_id'],
            'revision': record['revision'],
            'valid_at': record['valid_at'],
            'known_at': record['known_at'],
            'payload': {field: record['payload'][field] for field in permitted if field in record['payload']},
        })
    used_at = stamp(now())
    connection.execute(update(partner_grants).where(partner_grants.c.id == row['id']).values(
        last_used_at=used_at, access_count=partner_grants.c.access_count + 1))
    grant = _grant_public({**row, 'last_used_at': used_at, 'access_count': row['access_count'] + 1})
    return {'grant': {'id': grant['id'], 'name': grant['name'], 'expires_at': grant['expires_at'],
                      'call_ids': grant['call_ids']},
            'read_at': used_at, 'records': projected}