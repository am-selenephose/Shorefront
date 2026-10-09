"""Behavioral upgrade tests: configuration precedence and state preservation."""
import hashlib
import json
import os

import pytest

from shorefront_api.adapters import configured_live_adapters
from shorefront_api.security import (
    authenticate_integration_token,
    authenticate_token,
    configured_approvers,
)
from shorefront_api.storage import default_database_url


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch):
    for key in list(os.environ):
        if key.startswith(('SHOREFRONT_', 'PORTFLOW_')) or key == 'DATABASE_URL':
            monkeypatch.delenv(key)


def operator_config(token='migration-test-only'):
    return json.dumps([{
        'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'operator_id': 'migration-operator',
        'display_name': 'Migration operator',
        'role': 'operator',
    }])


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
def test_operator_configuration_accepts_canonical_and_legacy_keys(monkeypatch, prefix):
    monkeypatch.setenv(f'{prefix}_APPROVERS_JSON', operator_config())
    identity = authenticate_token('migration-test-only')
    assert identity is not None
    assert identity.operator_id == 'migration-operator'


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
def test_integration_configuration_accepts_canonical_and_legacy_keys(monkeypatch, prefix):
    monkeypatch.setenv(f'{prefix}_INTEGRATIONS_JSON', json.dumps([{
        'token_sha256': hashlib.sha256(b'integration-migration-only').hexdigest(),
        'integration_id': 'migration-integration',
        'display_name': 'Migration integration',
        'vessel_ids': ['v-aurora'],
    }]))
    identity = authenticate_integration_token('integration-migration-only')
    assert identity is not None
    assert identity.vessel_ids == ['v-aurora']


def test_new_authorization_configuration_replaces_legacy_authority(monkeypatch):
    monkeypatch.setenv('PORTFLOW_APPROVERS_JSON', operator_config('old'))
    monkeypatch.setenv('SHOREFRONT_APPROVERS_JSON', operator_config('new'))
    assert authenticate_token('old') is None
    assert authenticate_token('new') is not None


@pytest.mark.parametrize('canonical', ['', '{bad-json'])
def test_invalid_canonical_authorization_never_restores_legacy_authority(monkeypatch, canonical):
    monkeypatch.setenv('PORTFLOW_APPROVERS_JSON', operator_config())
    monkeypatch.setenv('SHOREFRONT_APPROVERS_JSON', canonical)
    with pytest.raises(RuntimeError, match='valid JSON'):
        configured_approvers()


def test_explicit_empty_canonical_feed_disables_legacy_feed(monkeypatch):
    monkeypatch.setenv('PORTFLOW_AIS_URL', 'https://legacy.invalid/ais')
    monkeypatch.setenv('SHOREFRONT_AIS_URL', '')
    assert 'live-ais' not in configured_live_adapters()


def test_canonical_feed_and_provider_take_precedence(monkeypatch):
    monkeypatch.setenv('PORTFLOW_AIS_URL', 'https://legacy.invalid/ais')
    monkeypatch.setenv('SHOREFRONT_AIS_URL', 'https://canonical.invalid/ais')
    monkeypatch.setenv('SHOREFRONT_AIS_PROVIDER', 'Canonical provider')
    adapter = configured_live_adapters()['live-ais']
    assert adapter.url == 'https://canonical.invalid/ais'
    assert adapter.provider == 'Canonical provider'


def test_fresh_default_database_uses_shorefront_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert default_database_url() == f'sqlite:///{tmp_path}/.data/shorefront.db'
    assert not (tmp_path / '.data' / 'portflow.db').exists()


@pytest.mark.parametrize('prefix', ['SHOREFRONT', 'PORTFLOW'])
@pytest.mark.parametrize('filename', ['shorefront.db', 'portflow.db'])
def test_existing_database_reused_without_rewrite(tmp_path, monkeypatch, prefix, filename):
    database = tmp_path / filename
    database.write_bytes(b'untouched stored evidence fixture')
    monkeypatch.setenv(f'{prefix}_DATA_DIR', str(tmp_path))
    assert default_database_url() == f'sqlite:///{database}'
    assert database.read_bytes() == b'untouched stored evidence fixture'
    assert list(tmp_path.iterdir()) == [database]


def test_ambiguous_databases_require_explicit_selection(tmp_path, monkeypatch):
    (tmp_path / 'shorefront.db').touch()
    (tmp_path / 'portflow.db').touch()
    monkeypatch.setenv('SHOREFRONT_DATA_DIR', str(tmp_path))
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        default_database_url()


def test_explicit_database_url_wins_over_ambiguous_directory(tmp_path, monkeypatch):
    (tmp_path / 'shorefront.db').touch()
    (tmp_path / 'portflow.db').touch()
    monkeypatch.setenv('SHOREFRONT_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///explicit.db')
    assert default_database_url() == 'sqlite:///explicit.db'


def test_canonical_data_directory_wins(tmp_path, monkeypatch):
    monkeypatch.setenv('PORTFLOW_DATA_DIR', str(tmp_path / 'old'))
    monkeypatch.setenv('SHOREFRONT_DATA_DIR', str(tmp_path / 'new'))
    assert default_database_url() == f'sqlite:///{tmp_path}/new/shorefront.db'
    assert not (tmp_path / 'old').exists()
