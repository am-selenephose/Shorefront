"""Opt-in disposable PostgreSQL verification; never use a customer database."""
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from shorefront_api.product_api import create_product_app
from test_product import BOOTSTRAP, ORIGIN, activate, bootstrap, headers, invite, setup_call, write


def test_postgres_commands_owner_and_backup_restore(tmp_path):
    configured = os.environ.get('SF_TEST_POSTGRES_URL')
    if not configured:
        pytest.skip('Set SF_TEST_POSTGRES_URL to a dedicated disposable PostgreSQL instance')
    url = make_url(configured)
    if not str(url.query.get('host', '')).startswith('/tmp/shorefront-product-pg.'):
        pytest.fail('PostgreSQL test requires its private disposable Unix socket directory')
    schema = 'sf_test_' + uuid4().hex
    restored = 'sf_restore_' + uuid4().hex
    engine = create_engine(url)
    # Schemas are generated identifiers on the explicitly dedicated test database.
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = url.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    app = create_product_app(database_url=scoped, installation_id='postgres-test', origin=ORIGIN, bootstrap_token=BOOTSTRAP)
    with TestClient(app, base_url=ORIGIN) as client:
        bootstrap(client)
        setup_call(client)
        assert write(client, 'vessel', 'pg-conflict-vessel', {'name':'Postgres Conflict Vessel','length_m':190}).status_code == 201
        operator = activate(app, invite(client))
        changed = write(operator, 'vessel', 'pg-conflict-vessel',
                        {'name':'Postgres Conflict Vessel','length_m':205}, revision=1)
        assert changed.status_code == 201, changed.text
        conflicts = client.get('/api/v1/reconciliation/conflicts').json()
        assert len(conflicts) == 1
        conflict = conflicts[0]
        resolved = client.post(
            f"/api/v1/reconciliation/conflicts/{conflict['id']}/resolve",
            headers=headers(client, 'pg-reconciliation-resolution'),
            json={'accepted_revision':1, 'note':'PostgreSQL test retained the registered vessel length.'},
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()['resolution_revision'] == 3
        cookie = client.cookies.get('shorefront_session')
        csrf = client.get('/api/v1/auth/me').json()['csrf_token']
        def writer(index):
            other = TestClient(app, base_url=ORIGIN)
            other.cookies.set('shorefront_session', cookie)
            return other.post('/api/v1/records/port', headers={'Origin':ORIGIN, 'X-CSRF-Token':csrf, 'Idempotency-Key':f'pg-{index}'}, json={
                'record_id':'concurrent-port', 'expected_revision':0, 'source':'PostgreSQL test', 'payload':{'name':f'Port {index}','timezone':'UTC'}}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(writer, [1,2])) == [201,409]
        packet_ids = []
        for question in ['Normal plan', 'Berth 100%_ready', 'Berth 100XXready']:
            result = client.post('/api/v1/decisions', headers=headers(client), json={'call_id':'call-one','question':question})
            assert result.status_code == 201, result.text
            packet_ids.append(result.json()['id'])
        assert [r['id'] for r in client.get('/api/v1/decisions', params={'q':'BERTH 100%_','limit':1}).json()] == [packet_ids[1]]
        assert len(client.get('/api/v1/decisions', params={'q':'call-one','state':'pending'}).json()) == 3
        assert client.get('/api/v1/decisions', params={'state':'approved'}).json() == []
        assert [r['id'] for r in client.get('/api/v1/decisions', params={'after':min(packet_ids)}).json()] == sorted(packet_ids)[1:]
        evidence = client.get('/api/v1/evidence').json()
        assert evidence['audit_valid'] is True
    env = {**os.environ, 'PGHOST':url.query['host'], 'PGPORT':str(url.port or 5432), 'PGUSER':url.username or 'shorefront_test', 'PGDATABASE':url.database or 'postgres'}
    dump = tmp_path / 'workspace.sql'
    subprocess.run(['pg_dump','--schema',schema,'--no-owner','--no-privileges','--file',str(dump)], env=env, check=True, capture_output=True)
    # Restore into a separate generated schema without deleting the original.
    # pg_dump emits this unique generated schema name only as an identifier here.
    restored_sql = dump.read_text().replace(schema, restored)
    subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1'], input=restored_sql, text=True, env=env, check=True, capture_output=True)
    restored_url = url.update_query_dict({'options':f'-csearch_path={restored}'}).render_as_string(hide_password=False)
    restored_app = create_product_app(database_url=restored_url, installation_id='postgres-test', origin=ORIGIN, bootstrap_token=BOOTSTRAP)
    with TestClient(restored_app, base_url=ORIGIN) as client:
        from test_product import PASSWORD
        assert client.post('/api/v1/auth/login', headers={'Origin':ORIGIN}, json={'email':'owner@example.test','password':PASSWORD}).status_code == 200
        assert client.get('/api/v1/evidence').json() == evidence
    with pytest.raises(RuntimeError, match='installation'):
        with TestClient(create_product_app(database_url=restored_url, installation_id='wrong-owner', origin=ORIGIN, bootstrap_token=BOOTSTRAP)):
            pass
    engine.dispose()
