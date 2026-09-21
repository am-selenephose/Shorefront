from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .models import HarborOverview, Incident, OperationsEvent, ReplayReceipt


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


class IncidentRow(Base):
    __tablename__ = "incident"
    incident_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
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
                select(EventRow).order_by(EventRow.sequence.desc()).limit(max(1, min(limit, 1000)))
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
                select(IncidentRow).order_by(IncidentRow.started_at.desc()).limit(max(1, min(limit, 1000)))
            ).all()
            return [Incident.model_validate_json(row.payload) for row in rows]

    def queue_outbound_event(self, event: OperationsEvent) -> bool:
        envelope_id = f"out-{event.id}"
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            existing = session.scalar(
                select(OutboundEnvelopeRow.envelope_id).where(OutboundEnvelopeRow.event_id == event.id)
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
                delivered = bool(deliver(event))
                if not delivered:
                    continue

                now = datetime.now(timezone.utc)
                row.acknowledged_at = now
                receipt_row = ReplayReceiptRow(
                    envelope_id=row.envelope_id,
                    event_id=row.event_id,
                    replayed_at=now,
                    delivery_status="acked",
                    attempts=row.attempts,
                )
                session.add(receipt_row)
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
            session.query(OutboundEnvelopeRow).delete()
            session.query(ReplayReceiptRow).delete()
            session.commit()
