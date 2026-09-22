from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import (
    HarborOverview,
    Incident,
    OperationsEvent,
    RecoveryApplicationReceipt,
    ReplayReceipt,
    VesselRuntimeEnvelope,
    VesselRuntimeIngestResult,
    VesselRuntimeIngestStatus,
)


class Base(DeclarativeBase):
    pass


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




class VesselRuntimeCursorRow(Base):
    __tablename__ = "vessel_runtime_cursor"
    vessel_runtime_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    last_source_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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


def default_database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    data_dir = Path(os.getenv("PORTFLOW_DATA_DIR", ".data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'portflow.db').resolve()}"


class OperationsStore:
    def __init__(self, database_url: str | None = None):
        url = database_url or default_database_url()
        kwargs = {"pool_pre_ping": True}
        if url.startswith("sqlite:"):
            kwargs["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **kwargs)

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)

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


    def ingest_vessel_runtime_envelope(
        self,
        envelope: VesselRuntimeEnvelope,
    ) -> VesselRuntimeIngestResult:
        genesis = "0" * 64
        now = datetime.now(timezone.utc)

        with Session(self.engine) as session:
            cursor = session.get(
                VesselRuntimeCursorRow,
                envelope.vessel_runtime_id,
            )
            current_sequence = cursor.last_source_sequence if cursor else 0
            current_hash = cursor.source_head_hash if cursor else genesis

            if envelope.last_source_sequence == current_sequence:
                if envelope.source_head_hash == current_hash:
                    return VesselRuntimeIngestResult(
                        vessel_runtime_id=envelope.vessel_runtime_id,
                        status=VesselRuntimeIngestStatus.DUPLICATE,
                        accepted_events=0,
                        last_source_sequence=current_sequence,
                        source_head_hash=current_hash,
                        detail="Envelope head already accepted",
                    )
                return VesselRuntimeIngestResult(
                    vessel_runtime_id=envelope.vessel_runtime_id,
                    status=VesselRuntimeIngestStatus.CONFLICT,
                    accepted_events=0,
                    last_source_sequence=current_sequence,
                    source_head_hash=current_hash,
                    detail="Envelope source head conflicts with stored cursor",
                )

            if envelope.after_sequence > current_sequence:
                return VesselRuntimeIngestResult(
                    vessel_runtime_id=envelope.vessel_runtime_id,
                    status=VesselRuntimeIngestStatus.GAP,
                    accepted_events=0,
                    last_source_sequence=current_sequence,
                    source_head_hash=current_hash,
                    detail="Envelope starts after the stored vessel-runtime cursor",
                )

            if envelope.after_sequence < current_sequence:
                return VesselRuntimeIngestResult(
                    vessel_runtime_id=envelope.vessel_runtime_id,
                    status=VesselRuntimeIngestStatus.CONFLICT,
                    accepted_events=0,
                    last_source_sequence=current_sequence,
                    source_head_hash=current_hash,
                    detail="Envelope starts behind the stored vessel-runtime cursor",
                )

            if envelope.base_source_hash != current_hash:
                return VesselRuntimeIngestResult(
                    vessel_runtime_id=envelope.vessel_runtime_id,
                    status=VesselRuntimeIngestStatus.CONFLICT,
                    accepted_events=0,
                    last_source_sequence=current_sequence,
                    source_head_hash=current_hash,
                    detail="Envelope base hash conflicts with stored vessel-runtime history",
                )

            accepted = 0
            for projected in envelope.events:
                event = projected.event
                existing = session.scalar(
                    select(EventRow).where(EventRow.event_id == event.id)
                )
                if existing is not None:
                    stored = OperationsEvent.model_validate_json(existing.payload)
                    if stored != event:
                        session.rollback()
                        return VesselRuntimeIngestResult(
                            vessel_runtime_id=envelope.vessel_runtime_id,
                            status=VesselRuntimeIngestStatus.CONFLICT,
                            accepted_events=0,
                            last_source_sequence=current_sequence,
                            source_head_hash=current_hash,
                            detail=f"Projected event id conflict: {event.id}",
                        )
                    continue

                session.add(EventRow(
                    event_id=event.id,
                    occurred_at=event.occurred_at,
                    category=event.category,
                    severity=event.severity.value,
                    payload=event.model_dump_json(),
                ))
                accepted += 1

            if cursor is None:
                cursor = VesselRuntimeCursorRow(
                    vessel_runtime_id=envelope.vessel_runtime_id,
                    source_mode=envelope.source_mode.value,
                    last_source_sequence=envelope.last_source_sequence,
                    source_head_hash=envelope.source_head_hash,
                    updated_at=now,
                )
                session.add(cursor)
            else:
                cursor.source_mode = envelope.source_mode.value
                cursor.last_source_sequence = envelope.last_source_sequence
                cursor.source_head_hash = envelope.source_head_hash
                cursor.updated_at = now

            session.commit()
            return VesselRuntimeIngestResult(
                vessel_runtime_id=envelope.vessel_runtime_id,
                status=VesselRuntimeIngestStatus.ACCEPTED,
                accepted_events=accepted,
                last_source_sequence=envelope.last_source_sequence,
                source_head_hash=envelope.source_head_hash,
            )

    def vessel_runtime_cursor(
        self,
        vessel_runtime_id: str,
    ) -> tuple[int, str] | None:
        with Session(self.engine) as session:
            cursor = session.get(VesselRuntimeCursorRow, vessel_runtime_id)
            if cursor is None:
                return None
            return cursor.last_source_sequence, cursor.source_head_hash

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
            session.query(VesselRuntimeCursorRow).delete()
            session.commit()
