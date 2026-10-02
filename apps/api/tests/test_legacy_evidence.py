"""Prove this rename can read evidence produced by the actual pre-rename code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import shorefront_api.simulator as runtime
from shorefront_api.models import HarborOverview, ScenarioRunEvidence
from shorefront_api.storage import OperationsStore

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/pre_rename_evidence.json').read_text())


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_pre_rename_snapshot_preserves_provenance_and_recovery_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, 'datetime', FrozenDateTime)
    store = OperationsStore(f'sqlite:///{tmp_path}/legacy.db')
    store.init_schema()
    snapshot = HarborOverview.model_validate(FIXTURE['snapshot'])
    store.save_snapshot(snapshot)
    reloaded = store.load_snapshot()
    assert reloaded.model_dump(mode='json') == FIXTURE['snapshot']
    restored = runtime.HarborSimulator(initial=reloaded)
    assert restored.port_name == 'PortFlow Demo Harbor'
    assert [s.provider for s in restored.data_sources] == [
        'PortFlow synthetic harbor generator',
        'PortFlow synthetic metocean generator',
        'PortFlow synthetic berth-plan generator',
        'PortFlow synthetic service-duration calibration',
    ]
    assert [e.model_dump(mode='json') for e in restored.events] == FIXTURE['snapshot']['events']
    assert restored._recovery_state_fingerprint('pc-aurora') == FIXTURE['restored_recovery_fingerprint']
    store.engine.dispose()


def test_pre_rename_evidence_roundtrip_and_export_keep_the_original_digest(tmp_path, monkeypatch):
    import shorefront_api.main as api
    store = OperationsStore(f'sqlite:///{tmp_path}/legacy-evidence.db')
    store.init_schema()
    evidence = ScenarioRunEvidence.model_validate(FIXTURE['evidence'])
    store.save_scenario_run_evidence(evidence)
    restored = store.get_scenario_run_evidence('identity-baseline-fixture')
    canonical = json.dumps(restored.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
    assert hashlib.sha256(canonical.encode()).hexdigest() == FIXTURE['evidence_sha256']
    monkeypatch.setattr(api, 'store', store)
    exported = api.scenario_run_evidence_pack('identity-baseline-fixture', identity=None)
    assert exported['pack_version'] == 'portflow-evidence-v1'
    assert exported['sha256'] == FIXTURE['evidence_sha256']
    assert exported['scenario_run'].model_dump(mode='json') == FIXTURE['evidence']
    store.engine.dispose()
