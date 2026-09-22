from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ValidationError

from .models import IntegrationIdentity, OperatorIdentity, OperatorRole


class ApproverRecord(BaseModel):
    token_sha256: str
    operator_id: str
    display_name: str
    role: OperatorRole


class IntegrationRecord(BaseModel):
    token_sha256: str
    integration_id: str
    display_name: str
    vessel_ids: list[str] = Field(min_length=1)


bearer = HTTPBearer(auto_error=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def configured_approvers() -> list[ApproverRecord]:
    raw = os.getenv("PORTFLOW_APPROVERS_JSON", "[]")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PORTFLOW_APPROVERS_JSON must be valid JSON") from exc

    if not isinstance(payload, list):
        raise RuntimeError("PORTFLOW_APPROVERS_JSON must be a JSON array")

    try:
        records = [ApproverRecord.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise RuntimeError("PORTFLOW_APPROVERS_JSON contains an invalid approver record") from exc

    for record in records:
        digest = record.token_sha256.lower().strip()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError("Approver token_sha256 must be a 64-character lowercase SHA-256 hex digest")
        record.token_sha256 = digest

    return records


def configured_integrations() -> list[IntegrationRecord]:
    raw = os.getenv("PORTFLOW_INTEGRATIONS_JSON", "[]")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PORTFLOW_INTEGRATIONS_JSON must be valid JSON") from exc

    if not isinstance(payload, list):
        raise RuntimeError("PORTFLOW_INTEGRATIONS_JSON must be a JSON array")

    try:
        records = [IntegrationRecord.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise RuntimeError(
            "PORTFLOW_INTEGRATIONS_JSON contains an invalid integration record"
        ) from exc

    for record in records:
        digest = record.token_sha256.lower().strip()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError(
                "Integration token_sha256 must be a 64-character lowercase SHA-256 hex digest"
            )
        record.token_sha256 = digest
        record.vessel_ids = sorted(set(record.vessel_ids))

    return records


def authenticate_integration_token(token: str) -> IntegrationIdentity | None:
    supplied = token_digest(token)
    for record in configured_integrations():
        if hmac.compare_digest(supplied, record.token_sha256):
            return IntegrationIdentity(
                integration_id=record.integration_id,
                display_name=record.display_name,
                vessel_ids=record.vessel_ids,
            )
    return None


def authenticate_token(token: str) -> OperatorIdentity | None:
    supplied = token_digest(token)
    for record in configured_approvers():
        if hmac.compare_digest(supplied, record.token_sha256):
            return OperatorIdentity(
                operator_id=record.operator_id,
                display_name=record.display_name,
                role=record.role,
            )
    return None


def current_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> OperatorIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Operator authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    identity = authenticate_token(credentials.credentials)
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid operator credential",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity


def recovery_approver(
    identity: OperatorIdentity = Depends(current_operator),
) -> OperatorIdentity:
    if identity.role not in {OperatorRole.OPERATOR, OperatorRole.SUPERVISOR}:
        raise HTTPException(
            status_code=403,
            detail="Operator or supervisor role required for recovery approval",
        )
    return identity



def current_integration(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> IntegrationIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Integration authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    identity = authenticate_integration_token(credentials.credentials)
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid integration credential",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity
