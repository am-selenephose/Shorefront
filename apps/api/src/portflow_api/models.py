from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field

class VesselStatus(StrEnum):
    INBOUND = "inbound"
    AT_ANCHOR = "at_anchor"
    MANEUVERING = "maneuvering"
    BERTHED = "berthed"
    OUTBOUND = "outbound"

class BerthStatus(StrEnum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    MAINTENANCE = "maintenance"

class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class LinkMode(StrEnum):
    FULL = "full"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE_EDGE = "offline_edge"

class Coordinate(BaseModel):
    lat: float
    lon: float

class Vessel(BaseModel):
    id: str
    name: str
    imo: str
    vessel_type: str
    status: VesselStatus
    position: Coordinate
    speed_knots: float = 0
    heading_deg: float = 0
    eta: datetime | None = None
    assigned_berth_id: str | None = None
    cargo_summary: str | None = None

class Berth(BaseModel):
    id: str
    name: str
    terminal: str
    status: BerthStatus
    max_length_m: int
    position: Coordinate
    vessel_id: str | None = None

class PortCallStage(BaseModel):
    code: str
    label: str
    planned_at: datetime
    actual_at: datetime | None = None
    state: str = "pending"
    dependency_codes: list[str] = Field(default_factory=list)

class PortCall(BaseModel):
    id: str
    vessel_id: str
    berth_id: str
    arrival_eta: datetime
    departure_eta: datetime
    stages: list[PortCallStage]
    delay_minutes: int = 0
    risk: RiskLevel = RiskLevel.LOW
    estimated_cost_exposure_usd: float = 0

class WeatherState(BaseModel):
    observed_at: datetime
    wind_knots: float
    gust_knots: float
    visibility_km: float
    wave_height_m: float
    tide_m: float
    restriction_active: bool
    restriction_reason: str | None = None

class ConnectivityState(BaseModel):
    mode: LinkMode
    primary_link: str
    fallback_link: str | None = None
    bandwidth_kbps: int
    queued_events: int = 0
    last_transition_at: datetime

class OperationsEvent(BaseModel):
    id: str
    occurred_at: datetime
    category: str
    severity: RiskLevel
    title: str
    message: str
    vessel_id: str | None = None
    berth_id: str | None = None
    port_call_id: str | None = None

class HarborOverview(BaseModel):
    generated_at: datetime
    port_name: str
    center: Coordinate
    vessels: list[Vessel]
    berths: list[Berth]
    port_calls: list[PortCall]
    weather: WeatherState
    connectivity: ConnectivityState
    events: list[OperationsEvent]
    metrics: dict[str, float | int]
    data_disclaimer: str
