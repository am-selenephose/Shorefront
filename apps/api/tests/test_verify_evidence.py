"""Offline verification uses exported bytes, never a trusted server verdict."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from test_product import customer, setup_call, preview, activate, invite, headers


@pytest.fixture
def evidence(customer):
    setup_call(customer)
    packet=preview(customer)
    supervisor=activate(customer.app,invite(customer,'supervisor'),'supervisor')
    response=supervisor.post(f"/api/v1/decisions/{packet['id']}/approve",headers=headers(supervisor),json={'option_id':'option-0','reason':'Recorded review'})
    assert response.status_code==200
    return customer.get('/api/v1/evidence').json()


def test_offline_verifier_accepts_real_export_without_trusting_server_flag(evidence):
    from shorefront_api.verify_evidence import verify
    evidence['audit_valid']=False
    result=verify(evidence,installation='customer-a',expected_root=evidence['audit_root'])
    assert result['valid'] is True
    assert result['versions']==5
    assert result['decisions']==1
    assert result['signed'] is False


@pytest.mark.parametrize('change',['record','omit_record','duplicate_record','option','receipt','omit_decision','audit','omit_audit','root','owner'])
def test_offline_verifier_rejects_tampering_or_missing_items(evidence,change):
    from shorefront_api.verify_evidence import verify
    data=deepcopy(evidence)
    if change=='record':data['versions'][0]['payload']['name']='Changed'
    elif change=='omit_record':data['versions'].pop()
    elif change=='duplicate_record':data['versions'].append(data['versions'][0])
    elif change=='option':data['decisions'][0]['options'][0]['shift_minutes']=999
    elif change=='receipt':data['decisions'][0]['receipt']['reason']='Changed'
    elif change=='omit_decision':data['decisions'].clear()
    elif change=='audit':data['audit'][0]['payload']='{}'
    elif change=='omit_audit':data['audit'].pop()
    elif change=='root':data['audit_root']='0'*64
    elif change=='owner':data['installation_id']='another-installation'
    assert verify(data,installation='customer-a')['valid'] is False


def test_out_of_band_root_rejects_valid_but_different_export(evidence):
    from shorefront_api.verify_evidence import verify
    assert verify(evidence,installation='customer-a',expected_root='0'*64)['valid'] is False


def test_cli_is_offline_reports_only_summary_and_rejects_duplicate_json_keys(evidence,tmp_path):
    module=Path(__file__).resolve().parents[1]/'src/shorefront_api/verify_evidence.py'
    path=tmp_path/'evidence.json'
    path.write_text(json.dumps(evidence))
    result=subprocess.run([sys.executable,str(module),str(path),'--installation','customer-a'],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['valid'] is True
    assert 'Customer Harbor' not in result.stdout
    path.write_text('{"audit":[],"audit":[]}')
    invalid=subprocess.run([sys.executable,str(module),str(path),'--installation','customer-a'],capture_output=True,text=True)
    assert invalid.returncode==1
    assert json.loads(invalid.stdout)['valid'] is False
    assert 'Traceback' not in invalid.stderr


def test_offline_verifier_binds_fact_conflicts_and_resolution_to_audit(customer):
    from shorefront_api.verify_evidence import verify
    from test_product import write
    original={'name':'MV Evidence Conflict','length_m':190}
    changed={'name':'MV Evidence Conflict','length_m':205}
    assert write(customer,'vessel','evidence-conflict-vessel',original).status_code==201
    operator=activate(customer.app,invite(customer))
    assert write(operator,'vessel','evidence-conflict-vessel',changed,revision=1).status_code==201
    pending=customer.get('/api/v1/reconciliation/conflicts').json()
    assert len(pending)==1
    conflict=pending[0]
    response=customer.post(
        f"/api/v1/reconciliation/conflicts/{conflict['id']}/resolve",
        headers=headers(customer,'verify-conflict-resolution'),
        json={'accepted_revision':2,'note':'Second source confirmed against the current terminal register.'},
    )
    assert response.status_code==200,response.text
    export=customer.get('/api/v1/evidence').json()
    assert verify(export,installation='customer-a')['valid'] is True

    for mutation in ('fields','baseline','resolution'):
        tampered=deepcopy(export)
        if mutation=='fields':
            tampered['conflicts'][0]['fields']=['name']
        elif mutation=='baseline':
            tampered['conflicts'][0]['baseline']['payload']['length_m']=999
        else:
            tampered['conflicts'][0]['resolution_note']='tampered resolution'
        assert verify(tampered,installation='customer-a')['valid'] is False
