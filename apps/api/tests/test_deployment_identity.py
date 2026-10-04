"""Render deployment configuration only. Never start containers or restore real data."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]


def environment(**settings):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('PORTFLOW_', 'SHOREFRONT_', 'COMPOSE_', 'DATABASE_'))}
    env.update(settings)
    return env


def render(tmp_path, settings, *, upgrade=False, tls=False, operational=False):
    if not shutil.which('docker'):
        pytest.skip('Docker Compose CLI required for configuration-only tests')
    command = ['docker', 'compose', '--env-file', '/dev/null', '-p', 'identity-test',
               '-f', str(ROOT / 'docker-compose.prod.yml')]
    if upgrade:
        command += ['-f', str(ROOT / 'docker-compose.upgrade.yml')]
    if tls:
        command += ['-f', str(ROOT / 'docker-compose.tls.yml')]
    if operational:
        command += ['-f', str(ROOT / 'docker-compose.operational.yml')]
    return subprocess.run(command + ['config', '--format', 'json'], cwd=tmp_path,
                          env=environment(**settings), text=True, capture_output=True)


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
def test_new_stack_uses_current_identity_with_either_setting_prefix(tmp_path, prefix):
    result = render(tmp_path, {f'{prefix}_DB_PASSWORD': 'test-only',
                               f'{prefix}_APPROVERS_JSON': '[]'})
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    database = config['services']['postgres']['environment']
    assert database['POSTGRES_DB'] == 'shorefront'
    assert database['POSTGRES_USER'] == 'shorefront'
    assert config['services']['api']['environment']['SHOREFRONT_APPROVERS_JSON'] == '[]'
    assert config['volumes']['shorefront_prod_pg']['name'] == 'identity-test_shorefront_prod_pg'
    healthcheck = config['services']['postgres']['healthcheck']['test'][1]
    # Compose must leave this expansion for the container, not the host shell.
    assert '$${POSTGRES_USER}' in healthcheck
    assert '$${POSTGRES_DB}' in healthcheck


def test_upgrade_requires_explicit_external_volume_and_existing_database(tmp_path):
    values = {'SHOREFRONT_DB_PASSWORD': 'test-only', 'SHOREFRONT_APPROVERS_JSON': '[]',
              'SHOREFRONT_EXISTING_PG_VOLUME': 'actual_old_portflow_prod_pg',
              'SHOREFRONT_DB_NAME': 'portflow', 'SHOREFRONT_DB_USER': 'portflow'}
    result = render(tmp_path, values, upgrade=True)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    volume = config['volumes']['shorefront_prod_pg']
    assert volume['external'] is True
    assert volume['name'] == 'actual_old_portflow_prod_pg'
    for service in ('api', 'migrate'):
        assert config['services'][service]['environment']['DATABASE_URL'] == (
            'postgresql+psycopg://portflow:test-only@postgres:5432/portflow')
    for required in ('SHOREFRONT_EXISTING_PG_VOLUME', 'SHOREFRONT_DB_NAME', 'SHOREFRONT_DB_USER'):
        missing = {key: value for key, value in values.items() if key != required}
        assert render(tmp_path, missing, upgrade=True).returncode != 0


def test_empty_canonical_value_does_not_resurrect_legacy_credential(tmp_path):
    result = render(tmp_path, {'SHOREFRONT_DB_PASSWORD': 'test-only',
                               'SHOREFRONT_APPROVERS_JSON': '', 'PORTFLOW_APPROVERS_JSON': '["legacy"]'})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['services']['api']['environment']['SHOREFRONT_APPROVERS_JSON'] == ''


def test_customer_deployment_requires_owner_and_origin_and_verifies_schema(tmp_path):
    values = {'SHOREFRONT_DB_PASSWORD':'test-only','SHOREFRONT_APPROVERS_JSON':'[]',
              'SHOREFRONT_INSTALLATION_ID':'customer-one','SHOREFRONT_ORIGIN':'https://port.example.test'}
    result = render(tmp_path, values, operational=True)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    for service in ('migrate', 'api'):
        env = config['services'][service]['environment']
        assert env['SHOREFRONT_RUNTIME_MODE'] == 'operational'
        assert env['SHOREFRONT_INSTALLATION_ID'] == 'customer-one'
        assert env['SHOREFRONT_ORIGIN'] == 'https://port.example.test'
    assert config['services']['api']['environment']['SHOREFRONT_SCHEMA_MODE'] == 'verify'
    assert config['services']['api']['environment']['SHOREFRONT_DEMO_CONTROLS'] == '0'
    for required in ('SHOREFRONT_INSTALLATION_ID','SHOREFRONT_ORIGIN'):
        assert render(tmp_path, {k:v for k,v in values.items() if k != required}, operational=True).returncode != 0


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
def test_tls_overlay_uses_same_canonical_template_variable(tmp_path, prefix):
    values = {f'{prefix}_DB_PASSWORD': 'test-only', f'{prefix}_APPROVERS_JSON': '[]',
              f'{prefix}_PUBLIC_HTTPS_ORIGIN': 'https://localhost:8443',
              f'{prefix}_TLS_CERT_FILE': '/tmp/test-only.crt',
              f'{prefix}_TLS_KEY_FILE': '/tmp/test-only.key'}
    result = render(tmp_path, values, tls=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['services']['web']['environment']['SHOREFRONT_PUBLIC_HTTPS_ORIGIN'] == 'https://localhost:8443'


def test_restore_refuses_without_explicit_confirmation(tmp_path):
    dump = tmp_path / 'test.dump'
    dump.write_bytes(b'not a real database')
    result = subprocess.run(['bash', str(ROOT / 'ops/restore-postgres.sh'), str(dump)],
                            env=environment(), text=True, capture_output=True)
    assert result.returncode == 3
    assert 'restore refused' in result.stderr


@pytest.fixture
def boot_guard(tmp_path):
    # Baseline boot has no preflight branch. Intercept its mutating commands so a
    # RED test cannot create/remove a real lock or install anything in /workspace.
    bin_dir = tmp_path / 'guard-bin'
    bin_dir.mkdir()
    for command in ('mkdir', 'rm', 'curl', 'cp', 'chmod'):
        executable = bin_dir / command
        executable.write_text('#!/bin/sh\nexit 93\n')
        executable.chmod(0o755)
    return str(bin_dir) + os.pathsep + os.environ['PATH']


def test_boot_refuses_unspecified_schema_before_any_installation(tmp_path, boot_guard):
    result = subprocess.run(['sh', str(ROOT / 'deploy/basicdeploy_boot.sh')],
                            cwd=tmp_path, env=environment(PATH=boot_guard, SHOREFRONT_BOOT_PREFLIGHT_ONLY='1'),
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert 'SHOREFRONT_DB_SCHEMA' in result.stderr
    assert [p.name for p in tmp_path.iterdir()] == ['guard-bin']


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
def test_boot_preflight_accepts_explicit_schema_and_has_no_side_effects(tmp_path, prefix, boot_guard):
    result = subprocess.run(['sh', str(ROOT / 'deploy/basicdeploy_boot.sh')],
                            cwd=tmp_path, env=environment(**{'PATH': boot_guard, f'{prefix}_DB_SCHEMA': 'portflow_portfolio',
                                'SHOREFRONT_BOOT_PREFLIGHT_ONLY': '1'}),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'preflight=ok' in result.stdout
    assert [p.name for p in tmp_path.iterdir()] == ['guard-bin']


@pytest.mark.parametrize('schema', ['', 'bad-schema', '1schema', 'x' * 64])
def test_invalid_canonical_schema_never_falls_back(tmp_path, boot_guard, schema):
    result = subprocess.run(['sh', str(ROOT / 'deploy/basicdeploy_boot.sh')],
                            env=environment(PATH=boot_guard, SHOREFRONT_BOOT_PREFLIGHT_ONLY='1',
                                SHOREFRONT_DB_SCHEMA=schema, PORTFLOW_DB_SCHEMA='valid_legacy'),
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert 'SHOREFRONT_DB_SCHEMA' in result.stderr


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
@pytest.mark.parametrize('operational', ['0', '1'])
def test_backup_uses_selected_project_and_container_database_identity(tmp_path, prefix, operational):
    # Substitute only external CLI/process boundaries. No Docker daemon is used.
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    docker = bin_dir / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
Path(os.environ['TEST_COMMAND_LOG']).write_text(json.dumps(args))
index = args.index('sh')
result = subprocess.run(args[index:], env=dict(os.environ, POSTGRES_USER='actual-user', POSTGRES_DB='actual-db'))
sys.exit(result.returncode)
''')
    docker.chmod(0o755)
    pg_dump = bin_dir / 'pg_dump'
    pg_dump.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
    pg_dump.chmod(0o755)
    envfile = tmp_path / 'chosen.env'
    envfile.touch()
    log = tmp_path / 'command.json'
    dump = tmp_path / 'output.dump'
    result = subprocess.run(['bash', str(ROOT / 'ops/backup-postgres.sh'), str(dump)],
                            env=environment(**{'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
                                'TEST_COMMAND_LOG': str(log), f'{prefix}_ENV_FILE': str(envfile),
                                f'{prefix}_COMPOSE_PROJECT': 'existing-project', 'SHOREFRONT_UPGRADE': '1',
                                'SHOREFRONT_OPERATIONAL': operational, 'SHOREFRONT_TLS': '1'}),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(dump.read_text()) == ['-U', 'actual-user', '-d', 'actual-db', '-Fc']
    args = json.loads(log.read_text())
    assert args[args.index('-p') + 1] == 'existing-project'
    assert args[args.index('--env-file') + 1] == str(envfile)
    assert str(ROOT / 'docker-compose.upgrade.yml') in args
    assert (str(ROOT / 'docker-compose.operational.yml') in args) is (operational == '1')
    assert str(ROOT / 'docker-compose.tls.yml') in args


@pytest.fixture
def restore_sandbox(tmp_path):
    # Only the external Docker boundary is substituted. The real restore script
    # selects overlays, orders operations, redirects the dump and handles errors.
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    docker = bin_dir / 'docker'
    docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['TEST_COMMAND_LOG']).open('a') as log:
    log.write(json.dumps(args) + '\\n')
if 'exec' in args:
    Path(os.environ['TEST_RESTORED_DUMP']).write_bytes(sys.stdin.buffer.read())
    sys.exit(int(os.environ.get('TEST_RESTORE_STATUS', '0')))
if 'run' in args:
    sys.exit(int(os.environ.get('TEST_MIGRATE_STATUS', '0')))
if 'config' in args:
    sys.exit(int(os.environ.get('TEST_CONFIG_STATUS', '0')))
''')
    docker.chmod(0o755)
    dump = tmp_path / 'source.dump'
    dump.write_bytes(b'test-only dump payload; never sent to PostgreSQL')
    envfile = tmp_path / 'customer.env'
    envfile.touch()
    log = tmp_path / 'commands.jsonl'
    restored = tmp_path / 'restored-by-fake-docker.dump'
    settings = {'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
                'TEST_COMMAND_LOG': str(log), 'TEST_RESTORED_DUMP': str(restored),
                'SHOREFRONT_ENV_FILE': str(envfile), 'SHOREFRONT_COMPOSE_PROJECT': 'customer-project',
                'SHOREFRONT_RESTORE_CONFIRM': 'YES', 'SHOREFRONT_UPGRADE': '1'}
    return dump, envfile, log, restored, settings


def run_restore(sandbox, **settings):
    dump, _, log, _, defaults = sandbox
    result = subprocess.run(['bash', str(ROOT / 'ops/restore-postgres.sh'), str(dump)],
                            env=environment(**(defaults | settings)), text=True, capture_output=True)
    commands = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return result, commands


@pytest.mark.parametrize('operational', ['0', '1'])
def test_restore_retains_selected_runtime_tls_and_database_target(restore_sandbox, operational):
    result, commands = run_restore(restore_sandbox, SHOREFRONT_OPERATIONAL=operational, SHOREFRONT_TLS='1')
    assert result.returncode == 0, result.stderr
    assert 'restore=complete' in result.stdout
    dump, envfile, _, restored, _ = restore_sandbox
    assert restored.read_bytes() == dump.read_bytes()
    assert len(commands) == 5
    for args in commands:
        assert args[args.index('-p') + 1] == 'customer-project'
        assert args[args.index('--env-file') + 1] == str(envfile)
        overlays = [args[i + 1] for i, value in enumerate(args) if value == '-f']
        expected = [str(ROOT / 'docker-compose.prod.yml'), str(ROOT / 'docker-compose.upgrade.yml')]
        if operational == '1':
            expected.append(str(ROOT / 'docker-compose.operational.yml'))
        expected.append(str(ROOT / 'docker-compose.tls.yml'))
        assert overlays == expected
    assert commands[0][-2:] == ['config', '-q']
    assert commands[1][-3:] == ['stop', 'web', 'api']
    assert commands[2][-6:] == ['exec', '-T', 'postgres', 'sh', '-c',
                               'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error --single-transaction']
    assert commands[3][-3:] == ['run', '--rm', 'migrate']
    assert commands[4][-4:] == ['up', '-d', 'api', 'web']


@pytest.mark.parametrize('selection', [None, '', 'true', 'operational'])
def test_restore_requires_explicit_runtime_selection_before_docker(restore_sandbox, selection):
    settings = {} if selection is None else {'SHOREFRONT_OPERATIONAL': selection}
    result, commands = run_restore(restore_sandbox, **settings)
    assert result.returncode != 0
    assert 'SHOREFRONT_OPERATIONAL' in result.stderr
    assert commands == []


@pytest.mark.parametrize(('setting', 'expected_count'), [('TEST_CONFIG_STATUS', 1),
                                                        ('TEST_RESTORE_STATUS', 3),
                                                        ('TEST_MIGRATE_STATUS', 4)])
def test_restore_failure_stops_before_restarting_services(restore_sandbox, setting, expected_count):
    result, commands = run_restore(restore_sandbox, SHOREFRONT_OPERATIONAL='1', **{setting: '72'})
    assert result.returncode == 72
    assert len(commands) == expected_count
    assert not any('up' in command for command in commands)
    assert 'restore=complete' not in result.stdout
