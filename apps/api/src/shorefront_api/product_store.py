"""Database-authoritative customer workspace; no process-global operational state."""
from contextlib import contextmanager
import hashlib
import json
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import (Column, Integer, MetaData, String, Table, Text, UniqueConstraint,
                        create_engine, insert, inspect, select, text, update)

from .product_models import INGESTIBLE_KINDS, RECORD_MODELS, REFERENCES, RecordCommand, now, stamp
from .product_coordination import authorize_transition, cancellation_preserves_party, participant_eligible
from .storage import normalize_database_url

metadata = MetaData()
installation = Table('sf_installation', metadata, Column('id', Integer, primary_key=True),
                     Column('owner', String(96), nullable=False), Column('version', Integer, nullable=False),
                     Column('bootstrap_expires_at', String(40), nullable=False))
users = Table('sf_user', metadata, Column('id', String(96), primary_key=True),
              Column('email', String(254), unique=True, nullable=False), Column('name', String(200), nullable=False),
              Column('password', Text, nullable=False), Column('role', String(24), nullable=False),
              Column('active', Integer, nullable=False), Column('created_at', String(40), nullable=False))
sessions = Table('sf_session', metadata, Column('digest', String(64), primary_key=True),
                 Column('user_id', String(96), nullable=False, index=True), Column('csrf', String(96), nullable=False),
                 Column('expires_at', String(40), nullable=False))
invitations = Table('sf_invitation', metadata, Column('digest', String(64), primary_key=True),
                    Column('email', String(254), nullable=False), Column('role', String(24), nullable=False),
                    Column('expires_at', String(40), nullable=False))
attempts = Table('sf_auth_attempt', metadata, Column('key', String(64), primary_key=True),
                 Column('count', Integer, nullable=False), Column('expires_at', String(40), nullable=False))
versions = Table('sf_record_version', metadata, Column('sequence', Integer, primary_key=True, autoincrement=True),
                 Column('kind', String(32), nullable=False), Column('record_id', String(96), nullable=False),
                 Column('revision', Integer, nullable=False), Column('valid_at', String(40), nullable=False, index=True),
                 Column('known_at', String(40), nullable=False, index=True), Column('source', Text, nullable=False),
                 Column('actor_id', String(96), nullable=False), Column('payload', Text, nullable=False),
                 UniqueConstraint('kind', 'record_id', 'revision'))
fact_conflicts = Table('sf_fact_conflict', metadata,
                       Column('id', String(96), primary_key=True),
                       Column('kind', String(32), nullable=False, index=True),
                       Column('record_id', String(96), nullable=False, index=True),
                       Column('baseline_revision', Integer, nullable=False),
                       Column('challenger_revision', Integer, nullable=False),
                       Column('fields', Text, nullable=False),
                       Column('detected_at', String(40), nullable=False, index=True),
                       Column('state', String(24), nullable=False, index=True),
                       Column('resolved_at', String(40), nullable=True),
                       Column('resolved_by', String(96), nullable=True),
                       Column('accepted_revision', Integer, nullable=True),
                       Column('resolution_note', Text, nullable=True),
                       Column('resolution_revision', Integer, nullable=True),
                       UniqueConstraint('kind', 'record_id', 'baseline_revision', 'challenger_revision'))
commands = Table('sf_command', metadata, Column('actor_id', String(96), primary_key=True),
                 Column('key', String(128), primary_key=True), Column('digest', String(64), nullable=False),
                 Column('response', Text, nullable=False))
audit = Table('sf_audit', metadata, Column('sequence', Integer, primary_key=True, autoincrement=True),
              Column('payload', Text, nullable=False), Column('previous_hash', String(64), nullable=False),
              Column('hash', String(64), nullable=False))
connection_sources = Table('sf_connection_source', metadata,
                           Column('id', String(96), primary_key=True),
                           Column('name', String(200), nullable=False),
                           Column('digest', String(64), unique=True, nullable=False),
                           Column('allowed_kinds', Text, nullable=False),
                           Column('active', Integer, nullable=False),
                           Column('created_by', String(96), nullable=False),
                           Column('created_at', String(40), nullable=False),
                           Column('expires_at', String(40), nullable=False),
                           Column('last_used_at', String(40), nullable=True),
                           Column('write_count', Integer, nullable=False))
partner_grants = Table('sf_partner_grant', metadata,
                       Column('id', String(96), primary_key=True),
                       Column('name', String(200), nullable=False),
                       Column('digest', String(64), unique=True, nullable=False),
                       Column('allowed_kinds', Text, nullable=False),
                       Column('field_rules', Text, nullable=False),
                       Column('call_ids', Text, nullable=False),
                       Column('active', Integer, nullable=False),
                       Column('created_by', String(96), nullable=False),
                       Column('created_at', String(40), nullable=False),
                       Column('expires_at', String(40), nullable=False),
                       Column('last_used_at', String(40), nullable=True),
                       Column('access_count', Integer, nullable=False))
partner_deliveries = Table('sf_partner_delivery', metadata,
                          Column('id', String(96), primary_key=True),
                          Column('grant_id', String(96), nullable=False, index=True),
                          Column('created_by', String(96), nullable=False),
                          Column('created_at', String(40), nullable=False),
                          Column('payload_digest', String(64), nullable=False),
                          Column('payload', Text, nullable=False),
                          Column('record_count', Integer, nullable=False),
                          Column('first_delivered_at', String(40), nullable=True),
                          Column('last_delivered_at', String(40), nullable=True),
                          Column('retrieval_count', Integer, nullable=False),
                          Column('acknowledged_at', String(40), nullable=True),
                          Column('acknowledged_digest', String(64), nullable=True),
                          Column('acknowledgement_note', Text, nullable=True))
source_standard_profiles = Table('sf_connection_source_profile', metadata,
                                 Column('source_id', String(96), primary_key=True),
                                 Column('profile_id', String(96), primary_key=True))
standard_events = Table('sf_standard_event', metadata,
                        Column('sequence', Integer, primary_key=True, autoincrement=True),
                        Column('source_id', String(96), nullable=False, index=True),
                        Column('profile_id', String(96), nullable=False, index=True),
                        Column('event_id', String(96), nullable=False, index=True),
                        Column('revision', Integer, nullable=False),
                        Column('external_key', String(96), nullable=False, index=True),
                        Column('event_updated_at', String(40), nullable=False),
                        Column('received_at', String(40), nullable=False),
                        Column('digest', String(64), nullable=False),
                        Column('state', String(24), nullable=False),
                        Column('payload', Text, nullable=False),
                        Column('materialized', Text, nullable=False),
                        UniqueConstraint('source_id', 'profile_id', 'event_id', 'revision'))


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def public_record(row) -> dict:
    result = dict(row)
    result['payload'] = json.loads(result['payload'])
    return result


class ProductStore:
    def __init__(self, database_url: str, installation_id: str):
        self.owner = installation_id
        url = normalize_database_url(database_url)
        options = {'connect_args': {'check_same_thread': False, 'timeout': 15}} if url.startswith('sqlite:') else {}
        self.engine = create_engine(url, pool_pre_ping=True, **options)

    @contextmanager
    def transaction(self):
        # Auth and the command share the same serialization point. SQLite and
        # PostgreSQL arbitrate writers across processes; no Python lock is relied on.
        with self.engine.connect() as connection:
            try:
                if self.engine.dialect.name == 'sqlite':
                    connection.exec_driver_sql('BEGIN IMMEDIATE')
                elif self.engine.dialect.name == 'postgresql':
                    connection.execute(text('SELECT pg_advisory_xact_lock(736467821)'))
                else:
                    raise RuntimeError('Operational storage supports SQLite or PostgreSQL')
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def initialize(self, *, migrate=True):
        # All entrypoints, including the trusted local admin CLI, must verify the
        # decision tables even when the HTTP application has not been imported.
        from . import product_decisions  # noqa: F401

        existing = set(inspect(self.engine).get_table_names())
        if 'sf_installation' in existing:
            with self.transaction() as connection:
                current = connection.execute(select(installation.c.owner, installation.c.version)).mappings().first()
                if current and current['owner'] != self.owner:
                    raise RuntimeError('Database installation owner mismatch; restore refused')
                if current and current['version'] != 1:
                    raise RuntimeError('Unsupported operational schema version')
                columns = {column['name'] for column in inspect(connection).get_columns('sf_installation')}
                if 'bootstrap_expires_at' not in columns:
                    if not migrate:
                        raise RuntimeError('Operational schema columns are incompatible: sf_installation; run the explicit migration first')
                    # Old installations have no trustworthy setup start time.
                    # Only the local operator may open a new window for them.
                    connection.execute(text("ALTER TABLE sf_installation ADD COLUMN bootstrap_expires_at VARCHAR(40) NOT NULL DEFAULT '1970-01-01T00:00:00.000000+00:00'"))
        if migrate:
            metadata.create_all(self.engine)
        elif set(metadata.tables) - existing:
            raise RuntimeError('Operational schema is missing; run the explicit migration first')
        inspector = inspect(self.engine)
        for table in metadata.sorted_tables:
            if {column.name for column in table.columns} - {column['name'] for column in inspector.get_columns(table.name)}:
                raise RuntimeError(f'Operational schema columns are incompatible: {table.name}')
        with self.transaction() as connection:
            current = connection.execute(select(installation)).mappings().first()
            if current is None:
                if not migrate:
                    raise RuntimeError('Operational schema owner has not been initialized')
                connection.execute(insert(installation).values(id=1, owner=self.owner, version=1,
                                                               bootstrap_expires_at=stamp(now() + timedelta(hours=24))))
            elif current['owner'] != self.owner:
                raise RuntimeError('Database installation owner mismatch; restore refused')
            elif current['version'] != 1:
                raise RuntimeError('Unsupported operational schema version')

    def add_audit(self, connection, actor_id: str, action: str, detail: dict):
        previous = connection.execute(select(audit.c.hash).order_by(audit.c.sequence.desc()).limit(1)).scalar_one_or_none() or '0' * 64
        payload = canonical({'actor_id': actor_id, 'action': action, 'detail': detail, 'known_at': stamp(now())})
        connection.execute(insert(audit).values(payload=payload, previous_hash=previous, hash=digest(previous + payload)))

    def snapshot(self, connection, known_at: datetime | None = None, valid_at: datetime | None = None):
        query = select(versions).where(versions.c.known_at <= stamp(known_at or now()), versions.c.valid_at <= stamp(valid_at or now()))
        rows = connection.execute(query.order_by(versions.c.valid_at, versions.c.sequence)).mappings()
        result = {}
        for row in rows:
            result[(row['kind'], row['record_id'])] = public_record(row)
        return sorted(result.values(), key=lambda row: (row['kind'], row['record_id']))

    def write_record(self, connection, actor, kind: str, command: RecordCommand, idempotency_key: str):
        if actor['role'] not in {'admin', 'operator', 'supervisor'}:
            raise HTTPException(403, 'Operational write permission required')
        model = RECORD_MODELS.get(kind)
        if model is None:
            raise HTTPException(404, 'Unknown record type')
        intent = digest(canonical({'kind': kind, **command.model_dump(mode='json')}))
        prior = connection.execute(select(commands).where(commands.c.actor_id == actor['id'], commands.c.key == idempotency_key)).mappings().first()
        if prior:
            if prior['digest'] != intent:
                raise HTTPException(409, 'Idempotency key already belongs to another command')
            return json.loads(prior['response'])
        try:
            payload = model.model_validate(command.payload).model_dump(mode='json')
        except ValidationError as exc:
            raise HTTPException(422, [{'loc': list(e['loc']), 'msg': e['msg']} for e in exc.errors()]) from exc
        latest = connection.execute(select(versions).where(versions.c.kind == kind, versions.c.record_id == command.record_id).order_by(versions.c.revision.desc()).limit(1)).mappings().first()
        revision = latest['revision'] if latest else 0
        if revision != command.expected_revision:
            raise HTTPException(409, f'Record changed; expected revision {revision}. Refresh before saving.')
        valid_at = command.valid_at or now()
        facts = {(r['kind'], r['record_id']): r for r in self.snapshot(connection, valid_at=valid_at)}
        for field, target_kind in REFERENCES.items():
            reference = payload.get(field)
            if reference and (target_kind, reference) not in facts:
                raise HTTPException(422, f'{field} must reference an existing effective {target_kind} record')
        for field in ('assignee_id', 'recipient_id'):
            assigned = payload.get(field)
            if not assigned:
                continue
            member = connection.execute(select(users).where(users.c.id == assigned)).mappings().first()
            if kind in {'handoff', 'commitment', 'obligation'}:
                cancelling = cancellation_preserves_party(kind, payload, public_record(latest) if latest else None, field)
                if not participant_eligible(member) and not cancelling:
                    raise HTTPException(422, f'{field} must be an active team member with operational write authority')
            elif not member or not member['active']:
                raise HTTPException(422, f'{field} must be an active team member')
        if kind in {'handoff', 'commitment', 'obligation'}:
            if command.valid_at is not None:
                raise HTTPException(422, 'Coordination transitions use server time; they cannot be backdated or scheduled')
            creator = connection.execute(select(versions.c.actor_id).where(versions.c.kind == kind, versions.c.record_id == command.record_id).order_by(versions.c.revision).limit(1)).scalar_one_or_none()
            authorize_transition(kind, actor, payload, public_record(latest) if latest else None, creator)
        if kind == 'outcome':
            if command.valid_at is not None:
                raise HTTPException(422, 'Outcome revisions use server time; record actual event times in the payload')
            if latest and json.loads(latest['payload'])['decision_id'] != payload['decision_id']:
                raise HTTPException(409, 'An outcome remains bound to its original decision; correct its observations instead')
            from .product_decisions import get_packet
            packet = get_packet(connection, payload['decision_id'])
            if not packet['receipt']:
                raise HTTPException(422, 'Observed outcomes must reference an approved decision')
            existing_outcome = next((r for r in facts.values() if r['kind'] == 'outcome' and r['payload']['decision_id'] == payload['decision_id']), None)
            if existing_outcome and existing_outcome['record_id'] != command.record_id:
                raise HTTPException(409, 'Correct the existing outcome instead of counting the same decision twice')
        row = dict(kind=kind, record_id=command.record_id, revision=revision + 1,
                   valid_at=stamp(valid_at), known_at=stamp(now()), source=command.source,
                   actor_id=actor['id'], payload=canonical(payload))
        result = connection.execute(insert(versions).values(**row))
        row['sequence'] = result.inserted_primary_key[0]
        response = public_record(row)
        if (latest and kind in INGESTIBLE_KINDS and latest['actor_id'] != actor['id']
                and not command.source.startswith('reconciliation:')
                and not command.source.startswith('Approved decision ')):
            previous_payload = json.loads(latest['payload'])
            fields = sorted(key for key in set(previous_payload) | set(payload)
                            if previous_payload.get(key) != payload.get(key))
            if fields:
                conflict_id = digest(canonical({
                    'kind': kind, 'record_id': command.record_id,
                    'baseline_revision': latest['revision'],
                    'challenger_revision': row['revision'],
                }))[:32]
                conflict = {
                    'id': conflict_id, 'kind': kind, 'record_id': command.record_id,
                    'baseline_revision': latest['revision'], 'challenger_revision': row['revision'],
                    'fields': canonical(fields), 'detected_at': stamp(now()), 'state': 'unresolved',
                    'resolved_at': None, 'resolved_by': None, 'accepted_revision': None,
                    'resolution_note': None, 'resolution_revision': None,
                }
                if connection.execute(select(fact_conflicts.c.id).where(
                        fact_conflicts.c.id == conflict_id)).scalar_one_or_none() is None:
                    connection.execute(insert(fact_conflicts).values(**conflict))
                    self.add_audit(connection, actor['id'], 'fact.conflict.detected', {
                        'id': conflict_id, 'kind': kind, 'record_id': command.record_id,
                        'baseline_revision': latest['revision'], 'challenger_revision': row['revision'],
                        'fields': fields,
                    })
        self.add_audit(connection, actor['id'], 'record.written', response)
        connection.execute(insert(commands).values(actor_id=actor['id'], key=idempotency_key, digest=intent, response=canonical(response)))
        return response

    def _public_fact_conflict(self, connection, row) -> dict:
        result = dict(row)
        result['fields'] = json.loads(result['fields'])
        candidates = {}
        for revision in (result['baseline_revision'], result['challenger_revision']):
            candidate = connection.execute(select(versions).where(
                versions.c.kind == result['kind'],
                versions.c.record_id == result['record_id'],
                versions.c.revision == revision,
            )).mappings().first()
            if candidate is None:
                raise RuntimeError('Fact conflict references a missing record version')
            candidates[revision] = public_record(candidate)
        result['baseline'] = candidates[result['baseline_revision']]
        result['challenger'] = candidates[result['challenger_revision']]
        return result

    def fact_conflict_list(self, connection, state: str = 'unresolved') -> list[dict]:
        query = select(fact_conflicts)
        if state != 'all':
            query = query.where(fact_conflicts.c.state == state)
        rows = connection.execute(query.order_by(
            fact_conflicts.c.detected_at.desc(), fact_conflicts.c.id)).mappings()
        return [self._public_fact_conflict(connection, row) for row in rows]

    def resolve_fact_conflict(self, connection, actor, conflict_id: str,
                              accepted_revision: int, note: str, idempotency_key: str) -> dict:
        if actor['role'] not in {'admin', 'operator', 'supervisor'}:
            raise HTTPException(403, 'Operational reconciliation authority required')
        intent = digest(canonical({
            'conflict_id': conflict_id, 'accepted_revision': accepted_revision, 'note': note,
        }))
        prior = connection.execute(select(commands).where(
            commands.c.actor_id == actor['id'], commands.c.key == idempotency_key
        )).mappings().first()
        if prior:
            if prior['digest'] != intent:
                raise HTTPException(409, 'Idempotency key already belongs to another command')
            return json.loads(prior['response'])

        row = connection.execute(select(fact_conflicts).where(
            fact_conflicts.c.id == conflict_id)).mappings().first()
        if row is None:
            raise HTTPException(404, 'Fact conflict not found')
        if row['state'] != 'unresolved':
            raise HTTPException(409, 'Fact conflict has already been resolved')
        candidates = {row['baseline_revision'], row['challenger_revision']}
        if accepted_revision not in candidates:
            raise HTTPException(422, 'Accepted revision must be one of the conflicting versions')

        accepted = connection.execute(select(versions).where(
            versions.c.kind == row['kind'],
            versions.c.record_id == row['record_id'],
            versions.c.revision == accepted_revision,
        )).mappings().first()
        if accepted is None:
            raise RuntimeError('Fact conflict references a missing accepted version')
        latest = connection.execute(select(versions).where(
            versions.c.kind == row['kind'], versions.c.record_id == row['record_id']
        ).order_by(versions.c.revision.desc()).limit(1)).mappings().first()

        resolution_revision = None
        if latest and latest['revision'] == row['challenger_revision'] and accepted_revision != latest['revision']:
            command = RecordCommand(
                record_id=row['record_id'],
                expected_revision=latest['revision'],
                source=f'reconciliation:{conflict_id}',
                payload=json.loads(accepted['payload']),
            )
            materialized = self.write_record(
                connection, actor, row['kind'], command,
                digest(f'reconciliation:{conflict_id}:{accepted_revision}'),
            )
            resolution_revision = materialized['revision']

        resolved_at = stamp(now())
        connection.execute(update(fact_conflicts).where(
            fact_conflicts.c.id == conflict_id).values(
                state='resolved', resolved_at=resolved_at, resolved_by=actor['id'],
                accepted_revision=accepted_revision, resolution_note=note,
                resolution_revision=resolution_revision,
            ))
        self.add_audit(connection, actor['id'], 'fact.conflict.resolved', {
            'id': conflict_id, 'kind': row['kind'], 'record_id': row['record_id'],
            'accepted_revision': accepted_revision, 'resolution_revision': resolution_revision,
            'note': note,
        })
        resolved = connection.execute(select(fact_conflicts).where(
            fact_conflicts.c.id == conflict_id)).mappings().one()
        response = self._public_fact_conflict(connection, resolved)
        connection.execute(insert(commands).values(
            actor_id=actor['id'], key=idempotency_key, digest=intent, response=canonical(response)))
        return response

    def evidence(self, connection):
        from .product_decisions import get_packet, packets
        rows = connection.execute(select(audit).order_by(audit.c.sequence)).mappings().all()
        previous = '0' * 64
        valid = True
        written = {}
        proposed = {}
        approved = {}
        detected_conflicts = {}
        resolved_conflicts = {}
        for row in rows:
            valid = valid and row['previous_hash'] == previous and row['hash'] == digest(previous + row['payload'])
            previous = row['hash']
            try:
                entry = json.loads(row['payload'])
                if entry.get('action') == 'record.written':
                    detail = entry['detail']
                    written[(detail['kind'], detail['record_id'], detail['revision'])] = detail
                elif entry.get('action') == 'decision.proposed':
                    proposed[entry['detail']['decision_id']] = entry['detail']['packet_digest']
                elif entry.get('action') == 'decision.approved':
                    approved[entry['detail']['decision_id']] = entry['detail']
                elif entry.get('action') == 'fact.conflict.detected':
                    detail = entry['detail']
                    detected_conflicts[detail['id']] = detail
                elif entry.get('action') == 'fact.conflict.resolved':
                    detail = entry['detail']
                    resolved_conflicts[detail['id']] = detail
            except (ValueError, KeyError, TypeError):
                valid = False
        saved = [public_record(row) for row in connection.execute(select(versions).order_by(versions.c.sequence)).mappings()]
        valid = valid and len(saved) == len(written) and all(written.get((r['kind'], r['record_id'], r['revision'])) == r for r in saved)
        decisions = [get_packet(connection, row.id) for row in connection.execute(select(packets.c.id).order_by(packets.c.id))]
        valid = valid and len(decisions) == len(proposed)
        for packet in decisions:
            original = {**packet, 'receipt': None}
            valid = valid and proposed.get(packet['id']) == digest(canonical(original)) and approved.get(packet['id']) == packet['receipt']
        conflicts = self.fact_conflict_list(connection, 'all')
        valid = valid and len(conflicts) == len(detected_conflicts)
        for conflict in conflicts:
            detected = {'id': conflict['id'], 'kind': conflict['kind'], 'record_id': conflict['record_id'],
                        'baseline_revision': conflict['baseline_revision'],
                        'challenger_revision': conflict['challenger_revision'], 'fields': conflict['fields']}
            valid = valid and detected_conflicts.get(conflict['id']) == detected
            resolved = resolved_conflicts.get(conflict['id'])
            if conflict['state'] == 'resolved':
                expected = {'id': conflict['id'], 'kind': conflict['kind'], 'record_id': conflict['record_id'],
                            'accepted_revision': conflict['accepted_revision'],
                            'resolution_revision': conflict['resolution_revision'],
                            'note': conflict['resolution_note']}
                valid = valid and resolved == expected
            else:
                valid = valid and resolved is None
        valid = valid and set(resolved_conflicts).issubset(set(detected_conflicts))
        return {'installation_id': self.owner, 'audit_valid': valid, 'audit_root': previous,
                'assurance': 'SHA-256 chain; not a digital signature or external timestamp',
                'audit': [dict(row) for row in rows],
                'decisions': decisions,
                'versions': saved,
                'conflicts': conflicts}


def graph(records):
    nodes = [{'id': f"{r['kind']}:{r['record_id']}", 'kind': r['kind'], 'record_id': r['record_id']} for r in records]
    edges = [{'source': f"{r['kind']}:{r['record_id']}", 'target': f"{target}:{r['payload'][field]}", 'relation': field}
             for r in records for field, target in REFERENCES.items() if r['payload'].get(field)]
    return {'nodes': nodes, 'edges': edges}
