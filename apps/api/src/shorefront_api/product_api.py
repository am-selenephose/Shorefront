"""Operational HTTP surface. Training routes and simulator state are not mounted."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import hmac
import json
import os
import secrets
from urllib.parse import urlsplit
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime
from sqlalchemy import JSON, cast, delete, insert, or_, select, type_coerce, update

from .config import setting
from .product_coordination import schedule_conflicts, coordination_actions
from .product_auth import (COOKIE, create_user, identify, login_attempt, public_user,
                           password_hash, password_valid, require_admin, require_origin, start_session)
from .product_models import (AcceptInvite, ApprovalRequest, Bootstrap, DecisionRequest, ImportBatch,
                             IntegrationBatch, Invitation, Login, PartnerDeliveryAck, PartnerGrantCreate,
                             PasswordChange, RecordCommand, SourceCreate, now, stamp)
from .product_decisions import approve_packet, create_packet, get_packet, packets, recall, remember
from .product_connections import (acknowledge_partner_delivery, create_partner_delivery,
                                  create_partner_grant, create_source, ingest_records,
                                  list_partner_deliveries, list_partner_grants, list_sources,
                                  partner_delivery_queue, partner_projection, pull_partner_delivery,
                                  reconcile_partner_delivery, revoke_partner_grant, revoke_source,
                                  rotate_partner_grant, rotate_source)
from .product_standards import (DCSA_PROFILE, ingest_dcsa_port_call, list_standard_events,
                                list_standard_profiles)
from .product_store import ProductStore, canonical, digest, graph, installation, invitations, public_record, sessions, users, versions
from .storage import default_database_url


def create_product_app(database_url=None, installation_id=None, origin=None, bootstrap_token=None):
    owner = installation_id or setting('INSTALLATION_ID', '')
    site = (origin or setting('ORIGIN', '')).rstrip('/')
    bootstrap_secret = bootstrap_token if bootstrap_token is not None else setting('BOOTSTRAP_TOKEN', '')
    store = ProductStore(database_url or default_database_url(), owner)
    parsed = urlsplit(site)
    secure = parsed.scheme == 'https'

    @asynccontextmanager
    async def lifespan(app):
        if not owner or len(owner) > 96:
            raise RuntimeError('Set a stable SHOREFRONT_INSTALLATION_ID before startup')
        if (not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username or
                not (secure or parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1', '::1'})):
            raise RuntimeError('Set SHOREFRONT_ORIGIN to an exact HTTPS origin (HTTP only on loopback)')
        schema_mode = setting('SCHEMA_MODE', 'migrate')
        if schema_mode not in {'migrate', 'verify'}:
            raise RuntimeError('SHOREFRONT_SCHEMA_MODE must be migrate or verify')
        store.initialize(migrate=schema_mode == 'migrate')
        try:
            yield
        finally:
            store.engine.dispose()

    app = FastAPI(title='Shorefront Operational Workspace', lifespan=lifespan)
    app.state.product_store = store

    @app.middleware('http')
    async def boundaries(request: Request, call_next):
        # Reject oversized/streamed writes before body buffering. Clients use JSON
        # with Content-Length; uploads use a separate bounded contract when added.
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            length = request.headers.get('content-length')
            if request.headers.get('transfer-encoding') or length is None:
                return Response(status_code=411)
            try:
                if int(length) < 0 or int(length) > 262144:
                    return Response(status_code=413)
            except ValueError:
                return Response(status_code=400)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/healthz')
    def health():
        return {'ok': True, 'service': 'shorefront-api', 'runtime_mode': 'operational'}

    @app.get('/readyz')
    def ready():
        with store.transaction() as connection:
            connection.execute(select(users.c.id).limit(1))
        return {'ok': True, 'runtime_mode': 'operational'}

    @app.get('/api/v1/runtime/capabilities')
    def capabilities():
        with store.transaction() as connection:
            needs_setup = connection.execute(select(users.c.id).limit(1)).first() is None
        return {'runtime_mode': 'operational', 'needs_setup': needs_setup, 'demo_controls_enabled': False,
                'advisory_only': True, 'production_ready': False, 'installation_model': 'dedicated'}

    @app.post('/api/v1/auth/bootstrap', status_code=201)
    def bootstrap(body: Bootstrap, request: Request, response: Response):
        require_origin(request, site)
        if len(bootstrap_secret) < 32 or not hmac.compare_digest(bootstrap_secret.encode(), body.bootstrap_token.encode()):
            raise HTTPException(403, 'Bootstrap is not authorized; ask the installation operator')
        with store.transaction() as connection:
            if connection.execute(select(users.c.id).limit(1)).first():
                raise HTTPException(409, 'Installation already initialized')
            expires_at = connection.execute(select(installation.c.bootstrap_expires_at).where(installation.c.id == 1)).scalar_one()
            if expires_at <= stamp(now()):
                raise HTTPException(403, 'Initial setup window expired; ask the installation operator to reopen setup')
            user = create_user(connection, body, 'admin')
            store.add_audit(connection, user['id'], 'installation.initialized', {'installation_id': owner})
            return start_session(connection, user, response, secure)

    @app.post('/api/v1/auth/login')
    def login(body: Login, request: Request, response: Response):
        require_origin(request, site)
        with store.transaction() as connection:
            user, status = login_attempt(connection, body.email, body.password, request.client.host if request.client else 'unknown')
            if user:
                old_token = request.cookies.get(COOKIE)
                if old_token:
                    connection.execute(delete(sessions).where(sessions.c.digest == digest(old_token), sessions.c.user_id == user['id']))
                result = start_session(connection, user, response, secure)
        if status != 200:
            raise HTTPException(status, 'Too many attempts; try again in five minutes' if status == 429 else 'Email or password is incorrect',
                                headers={'Retry-After': '300'} if status == 429 else None)
        return result

    @app.get('/api/v1/auth/me')
    def me(request: Request):
        with store.transaction() as connection:
            user, session = identify(connection, request)
            return {'user': public_user(user), 'csrf_token': session['csrf']}

    @app.post('/api/v1/auth/password')
    def change_password(body: PasswordChange, request: Request, response: Response):
        require_origin(request, site)
        with store.transaction() as connection:
            user, _ = identify(connection, request, mutation=True)
            if not password_valid(body.current_password, user['password']):
                raise HTTPException(403, 'Current password is incorrect')
            connection.execute(update(users).where(users.c.id == user['id']).values(password=password_hash(body.new_password)))
            connection.execute(delete(sessions).where(sessions.c.user_id == user['id']))
            store.add_audit(connection, user['id'], 'password.changed', {})
            return start_session(connection, user, response, secure)

    @app.post('/api/v1/auth/logout')
    def logout(request: Request, response: Response):
        require_origin(request, site)
        with store.transaction() as connection:
            _, session = identify(connection, request, mutation=True)
            connection.execute(delete(sessions).where(sessions.c.digest == session['digest']))
        response.delete_cookie(COOKIE, path='/', secure=secure, httponly=True, samesite='strict')
        return {'revoked': True}

    @app.post('/api/v1/auth/invitations', status_code=201)
    def invite(body: Invitation, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            user, _ = identify(connection, request, mutation=True)
            require_admin(user)
            if connection.execute(select(users.c.id).where(users.c.email == body.email)).first():
                raise HTTPException(409, 'An account already exists for this email')
            token = secrets.token_urlsafe(32)
            expires_at = stamp(now() + timedelta(hours=24))
            connection.execute(delete(invitations).where(invitations.c.email == body.email))
            connection.execute(insert(invitations).values(digest=digest(token), email=body.email, role=body.role, expires_at=expires_at))
            store.add_audit(connection, user['id'], 'invitation.created', {'email': body.email, 'role': body.role})
            return {'invitation_token': token, 'expires_at': expires_at, 'delivery': 'Share privately; no email was sent'}

    @app.post('/api/v1/auth/accept', status_code=201)
    def accept(body: AcceptInvite, request: Request, response: Response):
        require_origin(request, site)
        with store.transaction() as connection:
            invitation = connection.execute(select(invitations).where(invitations.c.digest == digest(body.invitation_token),
                invitations.c.email == body.email, invitations.c.expires_at > stamp(now()))).mappings().first()
            if not invitation:
                raise HTTPException(403, 'Invitation is invalid, expired or already used')
            user = create_user(connection, body, invitation['role'])
            connection.execute(delete(invitations).where(invitations.c.digest == invitation['digest']))
            store.add_audit(connection, user['id'], 'invitation.accepted', {'role': user['role']})
            return start_session(connection, user, response, secure)

    @app.get('/api/v1/team')
    def team(request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            return [public_user(row) for row in connection.execute(select(users).order_by(users.c.created_at)).mappings()]

    @app.post('/api/v1/team/{user_id}/revoke')
    def revoke(user_id: str, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            require_admin(actor)
            if user_id == actor['id']:
                raise HTTPException(409, 'You cannot revoke your own administrator account')
            target = connection.execute(select(users.c.id).where(users.c.id == user_id)).first()
            if not target:
                raise HTTPException(404, 'Team member not found')
            connection.execute(update(users).where(users.c.id == user_id).values(active=0))
            connection.execute(delete(sessions).where(sessions.c.user_id == user_id))
            store.add_audit(connection, actor['id'], 'membership.revoked', {'user_id': user_id})
        return {'revoked': True}

    @app.get('/api/v1/workspace')
    def workspace(request: Request, known_at: AwareDatetime | None = None, valid_at: AwareDatetime | None = None):
        with store.transaction() as connection:
            user, _ = identify(connection, request)
            records = store.snapshot(connection, known_at, valid_at)
        attention = [r for r in records if r['kind'] == 'task' and r['payload']['status'] != 'done']
        return {'runtime_mode': 'operational', 'installation_id': owner, 'records': records,
                'attention': sorted(attention, key=lambda r: r['payload']['due_at']),
                'read_at': stamp(now()), 'user': public_user(user)}

    @app.get('/api/v1/coordination')
    def coordination(request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            records = [r for r in store.snapshot(connection) if r['kind'] in {'handoff', 'commitment', 'obligation'}]
            creators = {(row.kind, row.record_id): row.actor_id for row in connection.execute(
                select(versions.c.kind, versions.c.record_id, versions.c.actor_id).where(
                    versions.c.revision == 1, versions.c.kind.in_(['handoff', 'commitment', 'obligation'])))}
            members = {row['id']: row for row in connection.execute(select(users)).mappings()}
            items = [{'record': r, 'creator_id': creators[(r['kind'], r['record_id'])],
                      'actions': coordination_actions(r, actor, creators[(r['kind'], r['record_id'])], members)} for r in records]
            items.sort(key=lambda item: (datetime.fromisoformat(item['record']['payload']['due_at']), item['record']['record_id']))
        return {'items': items, 'read_at': stamp(now())}

    @app.get('/api/v1/records/{kind}/{record_id}/head')
    def record_head(kind: str, record_id: str, request: Request):
        # The latest recorded revision is the write precondition, not necessarily
        # the effective workspace fact. Never change the two-clock snapshot here.
        with store.transaction() as connection:
            identify(connection, request)
            row = connection.execute(select(versions).where(
                versions.c.kind == kind, versions.c.record_id == record_id
            ).order_by(versions.c.revision.desc()).limit(1)).mappings().first()
            if row is None:
                raise HTTPException(404, 'Record not found')
            return public_record(row)

    @app.post('/api/v1/records/{kind}', status_code=201)
    def write(kind: str, body: RecordCommand, request: Request):
        require_origin(request, site)
        key = request.headers.get('idempotency-key', '')
        if not key or len(key) > 128:
            raise HTTPException(400, 'Supply an Idempotency-Key of 1 to 128 characters')
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return store.write_record(connection, actor, kind, body, key)

    def command_key(request):
        key = request.headers.get('idempotency-key', '')
        if not key or len(key) > 128:
            raise HTTPException(400, 'Supply an Idempotency-Key of 1 to 128 characters')
        return key

    @app.get('/api/v1/connections/sources')
    def connection_source_list(request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return list_sources(connection, actor)

    @app.post('/api/v1/connections/sources', status_code=201)
    def connection_source_create(body: SourceCreate, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return create_source(store, connection, actor, body)

    @app.post('/api/v1/connections/sources/{source_id}/revoke')
    def connection_source_revoke(source_id: str, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return revoke_source(store, connection, actor, source_id)

    @app.post('/api/v1/connections/sources/{source_id}/rotate', status_code=201)
    def connection_source_rotate(source_id: str, request: Request,
                                 expires_in_hours: int = Query(720, ge=1, le=8760)):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return rotate_source(store, connection, actor, source_id, expires_in_hours)

    @app.post('/api/v1/integrations/{source_id}/records', status_code=201)
    def integration_records(source_id: str, body: IntegrationBatch, request: Request):
        key = command_key(request)
        with store.transaction() as connection:
            return ingest_records(store, connection, request, source_id, body, key)

    @app.get('/api/v1/connections/standards')
    def connection_standard_profiles(request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return list_standard_profiles(connection, actor)

    @app.get('/api/v1/connections/standard-events')
    def connection_standard_event_list(request: Request, limit: int = Query(100, ge=1, le=500)):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return list_standard_events(connection, actor, limit=limit)

    @app.post('/api/v1/integrations/{source_id}/standards/{profile_id}/events', status_code=202)
    def integration_standard_events(source_id: str, profile_id: str, body: dict, request: Request):
        if profile_id != DCSA_PROFILE:
            raise HTTPException(404, 'Unknown operational standard profile')
        key = command_key(request)
        with store.transaction() as connection:
            return ingest_dcsa_port_call(store, connection, request, source_id, body, key)

    @app.get('/api/v1/connections/partner-grants')
    def partner_grant_list(request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return list_partner_grants(connection, actor)

    @app.post('/api/v1/connections/partner-grants', status_code=201)
    def partner_grant_create(body: PartnerGrantCreate, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return create_partner_grant(store, connection, actor, body)

    @app.post('/api/v1/connections/partner-grants/{grant_id}/revoke')
    def partner_grant_revoke(grant_id: str, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return revoke_partner_grant(store, connection, actor, grant_id)

    @app.post('/api/v1/connections/partner-grants/{grant_id}/rotate', status_code=201)
    def partner_grant_rotate(grant_id: str, request: Request,
                             expires_in_hours: int = Query(24, ge=1, le=2160)):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return rotate_partner_grant(store, connection, actor, grant_id, expires_in_hours)

    @app.get('/api/v1/connections/deliveries')
    def partner_delivery_admin_list(request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return list_partner_deliveries(connection, actor)

    @app.post('/api/v1/connections/partner-grants/{grant_id}/deliveries', status_code=201)
    def partner_delivery_create(grant_id: str, request: Request):
        require_origin(request, site)
        key = command_key(request)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return create_partner_delivery(store, connection, actor, grant_id, key)

    @app.get('/api/v1/connections/deliveries/{delivery_id}/reconciliation')
    def partner_delivery_reconciliation(delivery_id: str, request: Request):
        with store.transaction() as connection:
            actor, _ = identify(connection, request)
            return reconcile_partner_delivery(store, connection, actor, delivery_id)

    @app.get('/api/v1/partner/deliveries')
    def partner_delivery_list(request: Request):
        with store.transaction() as connection:
            return partner_delivery_queue(connection, request)

    @app.get('/api/v1/partner/deliveries/{delivery_id}')
    def partner_delivery_read(delivery_id: str, request: Request):
        with store.transaction() as connection:
            return pull_partner_delivery(store, connection, request, delivery_id)

    @app.post('/api/v1/partner/deliveries/{delivery_id}/acknowledge')
    def partner_delivery_ack(delivery_id: str, body: PartnerDeliveryAck, request: Request):
        key = command_key(request)
        with store.transaction() as connection:
            return acknowledge_partner_delivery(store, connection, request, delivery_id, body, key)

    @app.get('/api/v1/partner/projection')
    def partner_projection_read(request: Request):
        with store.transaction() as connection:
            return partner_projection(store, connection, request)

    @app.post('/api/v1/imports', status_code=201)
    def import_records(body: ImportBatch, request: Request):
        require_origin(request, site)
        key = command_key(request)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            if actor['role'] not in {'admin', 'operator', 'supervisor'}:
                raise HTTPException(403, 'Operational write permission required')
            intent = digest(canonical({'import': body.model_dump(mode='json')}))
            replay = recall(connection, actor, key, intent)
            if replay is not None:
                return replay
            results = [store.write_record(connection, actor, item.kind, item.command, digest(f'import:{key}:{index}')) for index, item in enumerate(body.records)]
            return remember(connection, actor, key, intent, {'records': results})

    @app.post('/api/v1/decisions', status_code=201)
    def propose(body: DecisionRequest, request: Request):
        require_origin(request, site)
        key = command_key(request)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return create_packet(store, connection, actor, body, key)

    @app.get('/api/v1/decisions')
    def decision_list(request: Request, limit: int = Query(100, ge=1, le=500),
                      after: str = Query('', max_length=96), q: str = Query('', max_length=200),
                      state: Literal['all', 'pending', 'approved'] = 'all'):
        with store.transaction() as connection:
            identify(connection, request)
            query = select(packets).where(packets.c.id > after)
            if state != 'all':
                query = query.where(packets.c.receipt.is_(None) if state == 'pending' else packets.c.receipt.is_not(None))
            if search := q.strip():
                # SQLite JSON lives as text; PostgreSQL requires an explicit cast.
                body = cast(packets.c.payload, JSON) if connection.dialect.name == 'postgresql' else type_coerce(packets.c.payload, JSON)
                query = query.where(or_(packets.c.id.icontains(search, autoescape=True),
                                        body['question'].as_string().icontains(search, autoescape=True),
                                        body['call_id'].as_string().icontains(search, autoescape=True)))
            rows = connection.execute(query.order_by(packets.c.id).limit(limit)).mappings()
            return [{**json.loads(row['payload']), 'receipt': json.loads(row['receipt']) if row['receipt'] else None} for row in rows]

    @app.get('/api/v1/decisions/{packet_id}')
    def decision_detail(packet_id: str, request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            return get_packet(connection, packet_id)

    @app.post('/api/v1/decisions/{packet_id}/approve')
    def approve(packet_id: str, body: ApprovalRequest, request: Request):
        require_origin(request, site)
        with store.transaction() as connection:
            actor, _ = identify(connection, request, mutation=True)
            return approve_packet(store, connection, actor, packet_id, body)

    @app.get('/api/v1/history')
    def history(request: Request, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        with store.transaction() as connection:
            identify(connection, request)
            return [public_record(row) for row in connection.execute(select(versions).where(versions.c.sequence > after).order_by(versions.c.sequence).limit(limit)).mappings()]

    @app.get('/api/v1/graph')
    def relationships(request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            return graph(store.snapshot(connection))

    @app.get('/api/v1/conflicts')
    def conflicts(request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            return schedule_conflicts(store.snapshot(connection))

    @app.get('/api/v1/outcomes')
    def outcomes(request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            observations = []
            for record in store.snapshot(connection):
                if record['kind'] != 'outcome':
                    continue
                body = record['payload']
                packet = get_packet(connection, body['decision_id'])
                option = next(o for o in packet['options'] if o['id'] == packet['receipt']['option_id'])
                expected = option['call_payload']
                arrival_error = (datetime.fromisoformat(body['actual_arrival']) - datetime.fromisoformat(expected['eta'])).total_seconds() / 60
                actual_duration = (datetime.fromisoformat(body['actual_departure']) - datetime.fromisoformat(body['actual_arrival'])).total_seconds() / 60
                planned_duration = (datetime.fromisoformat(expected['etd']) - datetime.fromisoformat(expected['eta'])).total_seconds() / 60
                observations.append({'record_id': record['record_id'], 'decision_id': body['decision_id'], 'source': record['source'],
                                     'arrival_error_minutes': arrival_error, 'occupancy_error_minutes': actual_duration - planned_duration})
        return {'confidence': 'descriptive_only', 'sample_count': len(observations), 'observations': observations,
                'mean_absolute_arrival_error_minutes': sum(abs(o['arrival_error_minutes']) for o in observations) / len(observations) if observations else None,
                'limitation': 'Operator-supplied outcomes; not a trained predictive model or evidence of causal savings'}

    @app.get('/api/v1/evidence')
    def evidence(request: Request):
        with store.transaction() as connection:
            identify(connection, request)
            return store.evidence(connection)

    static_dir = setting('STATIC_DIR', '')
    if static_dir:
        app.mount('/', StaticFiles(directory=os.path.abspath(static_dir), html=True), name='shorefront-frontend')
    return app
