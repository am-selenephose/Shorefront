from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

from .models import OperatorIdentity, OperatorRole


class ApproverRecord(BaseModel):
    token_sha256: str
    operator_id: str
    display_name: str
    role: OperatorRole


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


class VesselRuntimeCredential(BaseModel):
    token_sha256: str
    vessel_runtime_id: str
    display_name: str = "Vessel Runtime"


runtime_bearer = HTTPBearer(auto_error=False)


def configured_vessel_runtimes() -> list[VesselRuntimeCredential]:
    raw = os.getenv("PORTFLOW_VESSEL_RUNTIMES_JSON", "[]")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PORTFLOW_VESSEL_RUNTIMES_JSON must be valid JSON") from exc

    if not isinstance(payload, list):
        raise RuntimeError("PORTFLOW_VESSEL_RUNTIMES_JSON must be a JSON array")

    try:
        records = [VesselRuntimeCredential.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise RuntimeError(
            "PORTFLOW_VESSEL_RUNTIMES_JSON contains an invalid runtime record"
        ) from exc

    for record in records:
        digest = record.token_sha256.lower().strip()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise RuntimeError(
                "Vessel runtime token_sha256 must be a 64-character lowercase SHA-256 hex digest"
            )
        record.token_sha256 = digest
    return records


def vessel_runtime_sender(
    credentials: HTTPAuthorizationCredentials | None = Depends(runtime_bearer),
) -> VesselRuntimeCredential:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Vessel runtime authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supplied = token_digest(credentials.credentials)
    for record in configured_vessel_runtimes():
        if hmac.compare_digest(supplied, record.token_sha256):
            return record

    raise HTTPException(
        status_code=401,
        detail="Invalid vessel runtime credential",
        headers={"WWW-Authenticate": "Bearer"},
    )
