"""Operational standards gateway. Preserves external events before bounded native materialization."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy import insert, select, update

from .product_connections import _authenticated_source, _source_profiles
from .product_models import RecordCommand, now, stamp
from .product_store import (
    canonical,
    commands,
    connection_sources,
    digest,
    public_record,
    standard_events,
    versions,
)

DCSA_PROFILE = 'dcsa-port-call-2.0.0'
STANDARD_PROFILES = [{
    'id': DCSA_PROFILE,
    'standard': 'DCSA Port Call',
    'version': '2.0.0',
    'direction': 'inbound-events',
    'conformance': 'subset-not-certified',
    'native_materialization': ['vessel', 'call'],
    'notes': (
        'Validates and preserves DCSA Port Call 2.0 events. Native Shorefront materialization '
        'currently uses BERTH planning/actual timestamps plus vessel identity; other service events '
        'remain preserved standard evidence.'
    ),
}]


def _parse_time(value, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} is required')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{field} must be an ISO 8601 date-time') from exc
    if parsed.tzinfo is None:
        raise ValueError(f'{field} must include a timezone')
    return parsed.astimezone(timezone.utc)


def _uuid(value, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field} must be a UUID string')
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f'{field} must be a UUID') from exc


def _validate_dcsa_event(value, index: int) -> tuple[dict, str, str, datetime]:
    if not isinstance(value, dict):
        raise ValueError(f'events[{index}] must be an object')
    event_id = _uuid(value.get('eventID'), f'events[{index}].eventID')
    updated = _parse_time(value.get('eventUpdatedDateTime'), f'events[{index}].eventUpdatedDateTime')
    port_call = value.get('portCall')
    if not isinstance(port_call, dict):
        raise ValueError(f'events[{index}].portCall is required')
    call_id = _uuid(port_call.get('portCallID'), f'events[{index}].portCall.portCallID')

    service = value.get('portCallService')
    if service is not None and not isinstance(service, dict):
        raise ValueError(f'events[{index}].portCallService must be an object')
    timestamp = value.get('timestamp')
    if timestamp is not None:
        if not isinstance(timestamp, dict):
            raise ValueError(f'events[{index}].timestamp must be an object')
        classifier = timestamp.get('classifierCode')
        if classifier not in {'ACT', 'EST', 'PLN', 'REQ'}:
            raise ValueError(f'events[{index}].timestamp.classifierCode is unsupported')
        _parse_time(timestamp.get('serviceDateTime'), f'events[{index}].timestamp.serviceDateTime')
    vessel = value.get('vessel')
    if vessel is not None and not isinstance(vessel, dict):
        raise ValueError(f'events[{index}].vessel must be an object')
    if vessel and vessel.get('vesselIMONumber') is not None:
        imo = str(vessel['vesselIMONumber'])
        if len(imo) != 7 or not imo.isdigit():
            raise ValueError(f'events[{index}].vessel.vesselIMONumber must be a 7-digit IMO number')
    return value, event_id, call_id, updated


def _feedback(severity: str, message: str, index: int | None = None) -> dict:
    item = {'severity': severity, 'message': message}
    if index is not None:
        item['propertyPath'] = f'$.events[{index}]'
    return item


def list_standard_profiles(connection, actor) -> list[dict]:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    result = []
    for profile in STANDARD_PROFILES:
        event_count = connection.execute(
            select(standard_events.c.sequence).where(standard_events.c.profile_id == profile['id'])
        ).all()
        result.append({**profile, 'event_versions': len(event_count)})
    return result


def list_standard_events(connection, actor, *, limit: int = 100) -> list[dict]:
    if actor['role'] != 'admin':
        raise HTTPException(403, 'Administrator authority required')
    rows = connection.execute(
        select(standard_events).order_by(standard_events.c.sequence.desc()).limit(limit)
    ).mappings()
    return [{
        'sequence': row['sequence'],
        'source_id': row['source_id'],
        'profile_id': row['profile_id'],
        'event_id': row['event_id'],
        'revision': row['revision'],
        'external_key': row['external_key'],
        'event_updated_at': row['event_updated_at'],
        'received_at': row['received_at'],
        'state': row['state'],
        'materialized': json.loads(row['materialized']),
    } for row in rows]


def _latest_record(connection, kind: str, record_id: str):
    return connection.execute(
        select(versions)
        .where(versions.c.kind == kind, versions.c.record_id == record_id)
        .order_by(versions.c.revision.desc())
        .limit(1)
    ).mappings().first()


def _write_if_changed(store, connection, actor, source_id: str, kind: str, record_id: str, payload: dict):
    latest = _latest_record(connection, kind, record_id)
    if latest and json.loads(latest['payload']) == payload:
        return None
    revision = latest['revision'] if latest else 0
    command = RecordCommand(
        record_id=record_id,
        expected_revision=revision,
        source=f'standard:{DCSA_PROFILE}:{source_id}',
        payload=payload,
    )
    key = digest(canonical({
        'profile': DCSA_PROFILE,
        'source_id': source_id,
        'kind': kind,
        'record_id': record_id,
        'revision': revision,
        'payload': payload,
    }))
    return store.write_record(connection, actor, kind, command, key)


def _latest_call_events(connection, source_id: str, call_id: str) -> list[dict]:
    rows = connection.execute(
        select(standard_events)
        .where(
            standard_events.c.source_id == source_id,
            standard_events.c.profile_id == DCSA_PROFILE,
            standard_events.c.external_key == call_id,
        )
        .order_by(standard_events.c.sequence)
    ).mappings()
    latest = {}
    for row in rows:
        latest[row['event_id']] = dict(row)
    return list(latest.values())


def _event_sort(row: dict):
    return datetime.fromisoformat(row['event_updated_at']).astimezone(timezone.utc), row['sequence']


def _planning_timestamp(events: list[dict], event_type: str) -> str | None:
    rank = {'PLN': 3, 'EST': 2, 'REQ': 1}
    candidates = []
    for row in events:
        event = json.loads(row['payload'])
        service = event.get('portCallService') or {}
        timestamp = event.get('timestamp') or {}
        if (
            service.get('portCallServiceTypeCode') == 'BERTH'
            and service.get('portCallServiceEventTypeCode') == event_type
            and timestamp.get('classifierCode') in rank
        ):
            candidates.append((rank[timestamp['classifierCode']], _event_sort(row), timestamp['serviceDateTime']))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def _actual_exists(events: list[dict], event_type: str) -> bool:
    for row in events:
        event = json.loads(row['payload'])
        service = event.get('portCallService') or {}
        timestamp = event.get('timestamp') or {}
        if (
            service.get('portCallServiceTypeCode') == 'BERTH'
            and service.get('portCallServiceEventTypeCode') == event_type
            and timestamp.get('classifierCode') == 'ACT'
        ):
            return True
    return False


def _cancelled(events: list[dict]) -> bool:
    for row in events:
        event = json.loads(row['payload'])
        if (event.get('portCall') or {}).get('isOmitted') is True:
            return True
        service = event.get('portCallService') or {}
        if service.get('portCallServiceTypeCode') == 'BERTH' and service.get('isCanceled') is True:
            return True
    return False


def _latest_vessel(events: list[dict]) -> dict | None:
    candidates = []
    for row in events:
        event = json.loads(row['payload'])
        service = event.get('portCallService') or {}
        vessel = event.get('vessel') or {}
        if (
            service.get('portCallServiceTypeCode') == 'BERTH'
            and vessel.get('vesselIMONumber')
            and vessel.get('vesselName')
        ):
            candidates.append((_event_sort(row), vessel))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _meters(value, unit):
    if value is None:
        return None
    number = float(value)
    if unit == 'FOT':
        number *= 0.3048
    return round(number, 6)


def _materialize_dcsa_call(store, connection, source_row, call_id: str) -> tuple[list[dict], list[dict]]:
    events = _latest_call_events(connection, source_row['id'], call_id)
    feedback = []
    berth_events = [
        json.loads(row['payload']) for row in events
        if (json.loads(row['payload']).get('portCallService') or {}).get('portCallServiceTypeCode') == 'BERTH'
    ]
    if not berth_events:
        return [], [_feedback('INFO', 'Event retained. Native materialization currently supports BERTH service events only.')]

    eta = _planning_timestamp(events, 'ARRI')
    etd = _planning_timestamp(events, 'DEPA')
    if not eta or not etd:
        return [], [_feedback('INFO', 'Event retained; waiting for both berth arrival and departure planning timestamps.')]

    vessel = _latest_vessel(events)
    if not vessel:
        return [], [_feedback('WARN', 'Port call evidence is sufficient, but vessel IMO and name are required before native materialization.')]

    profiles = set(_source_profiles(connection, source_row['id']))
    if DCSA_PROFILE not in profiles:
        raise HTTPException(403, 'Connection is not granted this standard profile')
    allowed = set(json.loads(source_row['allowed_kinds']))
    needed = {'vessel', 'call'}
    if not needed <= allowed:
        return [], [_feedback('WARN', 'DCSA evidence retained, but this source is not allowed to materialize both vessel and call records.')]

    actor = {'id': f'integration:{source_row["id"]}', 'role': 'operator', 'active': 1}
    imo = str(vessel['vesselIMONumber'])
    vessel_id = f'imo_{imo}'
    vessel_payload = {
        'name': str(vessel['vesselName']),
        'imo': imo,
        'length_m': _meters(vessel.get('lengthOverall'), vessel.get('vesselSizeUnit')),
        'draft_m': _meters(vessel.get('draft'), vessel.get('draftUnit')),
    }
    vessel_payload = {key: value for key, value in vessel_payload.items() if value is not None}
    written = []
    vessel_record = _write_if_changed(store, connection, actor, source_row['id'], 'vessel', vessel_id, vessel_payload)
    if vessel_record:
        written.append(vessel_record)

    status = 'cancelled' if _cancelled(events) else (
        'departed' if _actual_exists(events, 'DEPA') else (
            'berthed' if _actual_exists(events, 'ARRI') else 'planned'
        )
    )
    call_payload = {
        'vessel_id': vessel_id,
        'berth_id': None,
        'eta': eta,
        'etd': etd,
        'status': status,
    }
    call_record = _write_if_changed(
        store, connection, actor, source_row['id'], 'call', f'dcsa_{call_id}', call_payload
    )
    if call_record:
        written.append(call_record)
    return written, feedback


def ingest_dcsa_port_call(store, connection, request: Request, source_id: str, body: dict, key: str) -> dict:
    source_row = _authenticated_source(connection, request, source_id)
    if DCSA_PROFILE not in set(_source_profiles(connection, source_id)):
        raise HTTPException(403, 'Connection is not granted this standard profile')
    if not isinstance(body, dict) or not isinstance(body.get('events'), list) or not (1 <= len(body['events']) <= 100):
        raise HTTPException(422, 'DCSA request requires an events array with 1 to 100 items')

    actor_id = f'standard:{source_id}:{DCSA_PROFILE}'
    intent = digest(canonical(body))
    prior = connection.execute(
        select(commands).where(commands.c.actor_id == actor_id, commands.c.key == key)
    ).mappings().first()
    if prior:
        if prior['digest'] != intent:
            raise HTTPException(409, 'Idempotency key already belongs to another standards request')
        return json.loads(prior['response'])

    accepted = 0
    feedback = []
    touched_calls = set()
    inserted_sequences = []
    received_at = stamp(now())

    for index, candidate in enumerate(body['events']):
        try:
            normalized, event_id, call_id, updated = _validate_dcsa_event(candidate, index)
        except ValueError as exc:
            feedback.append(_feedback('ERROR', str(exc), index))
            continue

        body_digest = digest(canonical(normalized))
        latest = connection.execute(
            select(standard_events)
            .where(
                standard_events.c.source_id == source_id,
                standard_events.c.profile_id == DCSA_PROFILE,
                standard_events.c.event_id == event_id,
            )
            .order_by(standard_events.c.revision.desc())
            .limit(1)
        ).mappings().first()

        if latest and latest['digest'] == body_digest:
            accepted += 1
            touched_calls.add(call_id)
            continue
        if latest:
            previous_updated = datetime.fromisoformat(latest['event_updated_at']).astimezone(timezone.utc)
            if updated <= previous_updated:
                feedback.append(_feedback(
                    'ERROR',
                    'Conflicting event revision was not newer than the preserved eventUpdatedDateTime.',
                    index,
                ))
                continue
            revision = latest['revision'] + 1
        else:
            revision = 1

        result = connection.execute(insert(standard_events).values(
            source_id=source_id,
            profile_id=DCSA_PROFILE,
            event_id=event_id,
            revision=revision,
            external_key=call_id,
            event_updated_at=stamp(updated),
            received_at=received_at,
            digest=body_digest,
            state='held',
            payload=canonical(normalized),
            materialized='[]',
        ))
        inserted_sequences.append(result.inserted_primary_key[0])
        accepted += 1
        touched_calls.add(call_id)

    materialized = []
    for call_id in sorted(touched_calls):
        try:
            records, notes = _materialize_dcsa_call(store, connection, source_row, call_id)
            materialized.extend(records)
            feedback.extend(notes)
        except HTTPException as exc:
            feedback.append(_feedback('ERROR', str(exc.detail)))

    state = 'materialized' if materialized else 'held'
    materialized_ids = [{'kind': row['kind'], 'record_id': row['record_id'], 'revision': row['revision']} for row in materialized]
    if inserted_sequences:
        connection.execute(
            update(standard_events)
            .where(standard_events.c.sequence.in_(inserted_sequences))
            .values(state=state, materialized=canonical(materialized_ids))
        )

    response = {
        'profile_id': DCSA_PROFILE,
        'accepted_events': accepted,
        'materialized_records': materialized,
        'feedbackElements': feedback,
    }
    connection.execute(insert(commands).values(
        actor_id=actor_id,
        key=key,
        digest=intent,
        response=canonical(response),
    ))
    connection.execute(
        update(connection_sources)
        .where(connection_sources.c.id == source_id)
        .values(
            last_used_at=received_at,
            write_count=connection_sources.c.write_count + len(materialized),
        )
    )
    store.add_audit(connection, actor_id, 'standard.events.ingested', {
        'profile_id': DCSA_PROFILE,
        'source_id': source_id,
        'accepted_events': accepted,
        'materialized_records': materialized_ids,
        'errors': sum(1 for item in feedback if item['severity'] == 'ERROR'),
    })
    return response
