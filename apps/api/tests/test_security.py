import hashlib
import json

import pytest

from shorefront_api.security import authenticate_token, configured_approvers


def test_security_config_rejects_invalid_json(monkeypatch):
    monkeypatch.setenv("PORTFLOW_APPROVERS_JSON", "{not-json")
    with pytest.raises(RuntimeError, match="valid JSON"):
        configured_approvers()


def test_security_config_rejects_non_sha256_digest(monkeypatch):
    monkeypatch.setenv(
        "PORTFLOW_APPROVERS_JSON",
        json.dumps([
            {
                "token_sha256": "not-a-digest",
                "operator_id": "ops-1",
                "display_name": "Ops One",
                "role": "operator",
            }
        ]),
    )
    with pytest.raises(RuntimeError, match="SHA-256"):
        configured_approvers()


def test_authenticate_token_returns_configured_identity(monkeypatch):
    token = "unit-test-operator"
    monkeypatch.setenv(
        "PORTFLOW_APPROVERS_JSON",
        json.dumps([
            {
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "operator_id": "ops-9",
                "display_name": "Ops Nine",
                "role": "supervisor",
            }
        ]),
    )

    identity = authenticate_token(token)
    assert identity is not None
    assert identity.operator_id == "ops-9"
    assert identity.display_name == "Ops Nine"
    assert identity.role.value == "supervisor"
    assert authenticate_token("wrong-token") is None
