from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .config import setting

from sqlalchemy import DateTime, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import (
    HarborOverview,
    Incident,
    OperationsEvent,
    RecoveryApplicationReceipt,
    RecoveryProposalEvidenceBatch,
    ReplayReceipt,
    ScenarioRunEvidence,
    VesselRuntimeEvent,
    VesselRuntimeEventRecord,
)


CURRENT_SCHEMA_VERSION = 3


class Base(DeclarativeBase):
    pass


class SchemaVersionRow(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SnapshotRow(Base):
    __tablename__ = "harbor_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventRow(Base):
    __tablename__ = "operations_event"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class IncidentRow(Base):
    __tablename__ = "incident"
    incident_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class RecoveryReceiptRow(Base):
    __tablename__ = "recovery_receipt"
    proposal_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    target_port_call_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class RecoveryProposalEvidenceRow(Base):
    __tablename__ = "recovery_proposal_evidence"
    evidence_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    requested_call_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    stale_parent_proposal_id: Mapped[str | None] = mapped_column(String(96), index=True, nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class ScenarioRunEvidenceRow(Base):
    __tablename__ = "scenario_run_evidence"
    run_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class VesselRuntimeEventRow(Base):
    __tablename__ = "vessel_runtime_event"
    event_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    integration_id: Mapped[str] = mapped_column(String(96), index=True, nullable=False)
    vessel_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    port_call_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class OutboundEnvelopeRow(Base):
    __tablename__ = "outbound_envelope"
    envelope_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)


class ReplayReceiptRow(Base):
    __tablename__ = "replay_receipt"
    envelope_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    replayed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def default_database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return normalize_database_url(configured)
    data_dir = Path(setting("DATA_DIR", ".data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    canonical = data_dir / "shorefront.db"
    legacy = data_dir / "portflow.db"
    if canonical.exists() and legacy.exists():
        raise RuntimeError(
            "Both current and legacy databases exist; set DATABASE_URL explicitly."
        )
    database = legacy if legacy.exists() else canonical
    return f"sqlite:///{database.resolve()}"


class OperationsStore:
    def __init__(self, database_url: str | None = None):
        url = (
            normalize_database_url(database_url)
            if database_url is not None
            else default_database_url()
        )
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite:"):
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **kwargs)

    @property
    def required_tables(self) -> set[str]:
        return set(Base.metadata.tables)

    def database_ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def schema_status(self) -> dict[str, object]:
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())
        missing = sorted(self.required_tables - existing)
        current_version: int | None = None

        if "schema_version" in existing:
            try:
                with Session(self.engine) as session:
                    row = session.get(SchemaVersionRow, 1)
                    if row is not None:
                        current_version = int(row.version)
            except Exception:
                current_version = None

        return {
            "database_reachable": self.database_ping(),
            "expected_version": CURRENT_SCHEMA_VERSION,
            "current_version": current_version,
            "missing_tables": missing,
            "compatible": (
                not missing
                and current_version == CURRENT_SCHEMA_VERSION
            ),
        }

    def migrate_schema(self) -> dict[str, object]:
        inspector = inspect(self.engine)
        existing_before = set(inspector.get_table_names())

        if "schema_version" in existing_before:
            with Session(self.engine) as session:
                row = session.get(SchemaVersionRow, 1)
                if row is not None and row.version > CURRENT_SCHEMA_VERSION:
                    raise RuntimeError(
                        "Database schema version "
                        f"{row.version} is newer than application version "
                        f"{CURRENT_SCHEMA_VERSION}"
                    )

        # v0 -> v1, v1 -> v2, and v2 -> v3 are additive migrations.
        # v2 adds immutable recovery/scenario evidence tables.
        # v3 adds immutable vessel-runtime integration events.
        # create_all only creates missing tables here; it does not alter existing tables.
        Base.metadata.create_all(self.engine)

        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            row = session.get(SchemaVersionRow, 1)
            if row is None:
                session.add(
                    SchemaVersionRow(
                        id=1,
                        version=CURRENT_SCHEMA_VERSION,
                        updated_at=now,
                    )
                )
            elif row.version < CURRENT_SCHEMA_VERSION:
                if row.version not in {0, 1, 2}:
                    raise RuntimeError(
                        "No migration path registered from schema version "
                        f"{row.version} to {CURRENT_SCHEMA_VERSION}"
                    )
                row.version = CURRENT_SCHEMA_VERSION
                row.updated_at = now
            session.commit()

        status = self.schema_status()
        if not bool(status["compatible"]):
            raise RuntimeError(f"Schema migration did not converge: {status}")
        return status

    def verify_schema(self) -> dict[str, object]:
        status = self.schema_status()
        if not bool(status["database_reachable"]):
            raise RuntimeError("Database is not reachable")
        if not bool(status["compatible"]):
            raise RuntimeError(
                "Database schema is not compatible with this Shorefront build: "
                f"{status}"
            )
        return status

    def init_schema(self) -> None:
        # Backward-compatible test/dev helper. Production startup uses the
        # explicit migrate command followed by verify mode.
        self.migrate_schema()

    def save_snapshot(self, overview: HarborOverview) -> None:
        payload = overview.model_dump_json()
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            row = session.get(SnapshotRow, 1)
            if row is None:
                session.add(SnapshotRow(id=1, payload=payload, updated_at=now))
            else:
                row.payload = payload
                row.updated_at = now
            session.commit()

    def load_snapshot(self) -> HarborOverview | None:
        with Session(self.engine) as session:
            row = session.get(SnapshotRow, 1)
            if row is None:
                return None
            return HarborOverview.model_validate_json(row.payload)

    def append_event(self, event: OperationsEvent) -> bool:
        with Session(self.engine) as session:
            exists = session.scalar(select(EventRow.sequence).where(EventRow.event_id == event.id))
            if exists is not None:
                return False
            session.add(EventRow(
                event_id=event.id,
                occurred_at=event.occurred_at,
                category=event.category,
                severity=event.severity.value,
                payload=event.model_dump_json(),
            ))
            session.commit()
            return True

    def list_events(self, limit: int = 100) -> list[OperationsEvent]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(EventRow)
                .order_by(EventRow.sequence.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [OperationsEvent.model_validate_json(row.payload) for row in rows]

    def upsert_incident(self, incident: Incident) -> None:
        with Session(self.engine) as session:
            row = session.get(IncidentRow, incident.id)
            if row is None:
                session.add(IncidentRow(
                    incident_id=incident.id,
                    status=incident.status.value,
                    started_at=incident.started_at,
                    payload=incident.model_dump_json(),
                ))
            else:
                row.status = incident.status.value
                row.payload = incident.model_dump_json()
            session.commit()

    def list_incidents(self, limit: int = 100) -> list[Incident]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(IncidentRow)
                .order_by(IncidentRow.started_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [Incident.model_validate_json(row.payload) for row in rows]

    def save_recovery_receipt(self, receipt: RecoveryApplicationReceipt) -> bool:
        with Session(self.engine) as session:
            if session.get(RecoveryReceiptRow, receipt.proposal_id) is not None:
                return False
            session.add(RecoveryReceiptRow(
                proposal_id=receipt.proposal_id,
                applied_at=receipt.applied_at,
                target_port_call_id=receipt.target_port_call_id,
                payload=receipt.model_dump_json(),
            ))
            session.commit()
            return True

    def list_recovery_receipts(self, limit: int = 100) -> list[RecoveryApplicationReceipt]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RecoveryReceiptRow)
                .order_by(RecoveryReceiptRow.applied_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [
                RecoveryApplicationReceipt.model_validate_json(row.payload)
                for row in rows
            ]

    def save_recovery_proposal_evidence(
        self,
        evidence: RecoveryProposalEvidenceBatch,
    ) -> bool:
        with Session(self.engine) as session:
            if session.get(RecoveryProposalEvidenceRow, evidence.evidence_id) is not None:
                return False
            session.add(
                RecoveryProposalEvidenceRow(
                    evidence_id=evidence.evidence_id,
                    generated_at=evidence.generated_at,
                    requested_call_id=evidence.requested_call_id,
                    stale_parent_proposal_id=evidence.stale_parent_proposal_id,
                    payload=evidence.model_dump_json(),
                )
            )
            session.commit()
            return True

    def list_recovery_proposal_evidence(
        self,
        limit: int = 100,
    ) -> list[RecoveryProposalEvidenceBatch]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(RecoveryProposalEvidenceRow)
                .order_by(RecoveryProposalEvidenceRow.generated_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [
                RecoveryProposalEvidenceBatch.model_validate_json(row.payload)
                for row in rows
            ]

    def save_scenario_run_evidence(
        self,
        evidence: ScenarioRunEvidence,
    ) -> bool:
        with Session(self.engine) as session:
            if session.get(ScenarioRunEvidenceRow, evidence.run_id) is not None:
                return False
            session.add(
                ScenarioRunEvidenceRow(
                    run_id=evidence.run_id,
                    scenario_id=evidence.scenario.id,
                    ran_at=evidence.ran_at,
                    payload=evidence.model_dump_json(),
                )
            )
            session.commit()
            return True

    def list_scenario_run_evidence(
        self,
        limit: int = 100,
        scenario_id: str | None = None,
    ) -> list[ScenarioRunEvidence]:
        with Session(self.engine) as session:
            query = select(ScenarioRunEvidenceRow)
            if scenario_id is not None:
                query = query.where(
                    ScenarioRunEvidenceRow.scenario_id == scenario_id
                )
            rows = session.scalars(
                query
                .order_by(ScenarioRunEvidenceRow.ran_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [
                ScenarioRunEvidence.model_validate_json(row.payload)
                for row in rows
            ]

    def get_scenario_run_evidence(
        self,
        run_id: str,
    ) -> ScenarioRunEvidence | None:
        with Session(self.engine) as session:
            row = session.get(ScenarioRunEvidenceRow, run_id)
            if row is None:
                return None
            return ScenarioRunEvidence.model_validate_json(row.payload)

    def save_vessel_runtime_event(
        self,
        record: VesselRuntimeEventRecord,
    ) -> bool:
        event = record.event
        with Session(self.engine) as session:
            if session.get(VesselRuntimeEventRow, event.event_id) is not None:
                return False
            session.add(
                VesselRuntimeEventRow(
                    event_id=event.event_id,
                    integration_id=record.integration_id,
                    vessel_id=event.vessel_id,
                    port_call_id=event.port_call_id,
                    event_type=event.event_type.value,
                    occurred_at=event.occurred_at,
                    received_at=record.received_at,
                    payload=record.model_dump_json(),
                )
            )
            session.commit()
            return True

    def get_vessel_runtime_event(
        self,
        event_id: str,
    ) -> VesselRuntimeEventRecord | None:
        with Session(self.engine) as session:
            row = session.get(VesselRuntimeEventRow, event_id)
            if row is None:
                return None
            return VesselRuntimeEventRecord.model_validate_json(row.payload)

    def list_vessel_runtime_events(
        self,
        limit: int = 100,
        integration_id: str | None = None,
        vessel_id: str | None = None,
    ) -> list[VesselRuntimeEventRecord]:
        with Session(self.engine) as session:
            query = select(VesselRuntimeEventRow)
            if integration_id is not None:
                query = query.where(
                    VesselRuntimeEventRow.integration_id == integration_id
                )
            if vessel_id is not None:
                query = query.where(
                    VesselRuntimeEventRow.vessel_id == vessel_id
                )
            rows = session.scalars(
                query
                .order_by(VesselRuntimeEventRow.received_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [
                VesselRuntimeEventRecord.model_validate_json(row.payload)
                for row in rows
            ]

    def queue_outbound_event(self, event: OperationsEvent) -> bool:
        envelope_id = f"out-{event.id}"
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            existing = session.scalar(
                select(OutboundEnvelopeRow.envelope_id)
                .where(OutboundEnvelopeRow.event_id == event.id)
            )
            if existing is not None:
                return False
            session.add(OutboundEnvelopeRow(
                envelope_id=envelope_id,
                event_id=event.id,
                queued_at=now,
                payload=event.model_dump_json(),
                attempts=0,
                acknowledged_at=None,
            ))
            session.commit()
            return True

    def pending_outbound_count(self) -> int:
        with Session(self.engine) as session:
            return len(session.scalars(
                select(OutboundEnvelopeRow.envelope_id)
                .where(OutboundEnvelopeRow.acknowledged_at.is_(None))
            ).all())

    def pending_outbound_events(self, limit: int = 1000) -> list[OperationsEvent]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(OutboundEnvelopeRow)
                .where(OutboundEnvelopeRow.acknowledged_at.is_(None))
                .order_by(OutboundEnvelopeRow.queued_at.asc())
                .limit(max(1, min(limit, 5000)))
            ).all()
            return [OperationsEvent.model_validate_json(row.payload) for row in rows]

    def replay_outbound_events(
        self,
        deliver: Callable[[OperationsEvent], bool],
        limit: int = 1000,
    ) -> list[ReplayReceipt]:
        receipts: list[ReplayReceipt] = []
        with Session(self.engine) as session:
            rows = session.scalars(
                select(OutboundEnvelopeRow)
                .where(OutboundEnvelopeRow.acknowledged_at.is_(None))
                .order_by(OutboundEnvelopeRow.queued_at.asc())
                .limit(max(1, min(limit, 5000)))
            ).all()

            for row in rows:
                existing_receipt = session.get(ReplayReceiptRow, row.envelope_id)
                if existing_receipt is not None:
                    if row.acknowledged_at is None:
                        row.acknowledged_at = existing_receipt.replayed_at
                    receipts.append(ReplayReceipt(
                        envelope_id=existing_receipt.envelope_id,
                        event_id=existing_receipt.event_id,
                        replayed_at=existing_receipt.replayed_at,
                        delivery_status=existing_receipt.delivery_status,
                        attempts=existing_receipt.attempts,
                    ))
                    continue

                row.attempts += 1
                event = OperationsEvent.model_validate_json(row.payload)
                if not bool(deliver(event)):
                    continue

                now = datetime.now(timezone.utc)
                row.acknowledged_at = now
                session.add(ReplayReceiptRow(
                    envelope_id=row.envelope_id,
                    event_id=row.event_id,
                    replayed_at=now,
                    delivery_status="acked",
                    attempts=row.attempts,
                ))
                receipts.append(ReplayReceipt(
                    envelope_id=row.envelope_id,
                    event_id=row.event_id,
                    replayed_at=now,
                    delivery_status="acked",
                    attempts=row.attempts,
                ))

            session.commit()

        return receipts

    def list_replay_receipts(self, limit: int = 100) -> list[ReplayReceipt]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(ReplayReceiptRow)
                .order_by(ReplayReceiptRow.replayed_at.desc())
                .limit(max(1, min(limit, 1000)))
            ).all()
            return [
                ReplayReceipt(
                    envelope_id=row.envelope_id,
                    event_id=row.event_id,
                    replayed_at=row.replayed_at,
                    delivery_status=row.delivery_status,
                    attempts=row.attempts,
                )
                for row in rows
            ]

    def clear_demo_state(self) -> None:
        with Session(self.engine) as session:
            session.query(SnapshotRow).delete()
            session.query(EventRow).delete()
            session.query(IncidentRow).delete()
            session.query(RecoveryReceiptRow).delete()
            session.query(OutboundEnvelopeRow).delete()
            session.query(ReplayReceiptRow).delete()
            session.commit()
