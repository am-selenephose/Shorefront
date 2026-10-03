from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, Field, model_validator


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


class IncidentType(StrEnum):
    PILOT_DELAY = "pilot_delay"
    TUG_UNAVAILABLE = "tug_unavailable"
    BUNKER_UNAVAILABLE = "bunker_unavailable"
    BERTH_OVERRUN = "berth_overrun"
    WIND_RESTRICTION = "wind_restriction"
    CONNECTIVITY_LOSS = "connectivity_loss"


class IncidentStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class ServiceKind(StrEnum):
    PILOT = "pilot"
    TUG = "tug"
    BERTH = "berth"
    CRANE = "crane"
    CARGO = "cargo"
    BUNKER = "bunker"
    STORES = "stores"
    DOCUMENTS = "documents"
    CUSTOMS = "customs"
    GATE = "gate"
    DEPARTURE = "departure"


class ServiceState(StrEnum):
    READY = "ready"
    ASSIGNED = "assigned"
    DELAYED = "delayed"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class ResourceStatus(StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    DELAYED = "delayed"
    UNAVAILABLE = "unavailable"


class RecoveryActionType(StrEnum):
    REASSIGN_RESOURCE = "reassign_resource"
    MOVE_BERTH = "move_berth"
    SHIFT_WINDOW = "shift_window"


class OperatorRole(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    SUPERVISOR = "supervisor"


class DecisionConfidence(StrEnum):
    DEMO = "demo"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ScenarioActionType(StrEnum):
    INCIDENT = "incident"
    CONNECTIVITY = "connectivity"


class VesselRuntimeEventType(StrEnum):
    POSITION = "position"
    ETA = "eta"
    READINESS = "readiness"
    CONSTRAINT = "constraint"
    CONNECTIVITY = "connectivity"


class DataSourceMode(StrEnum):
    SYNTHETIC = "synthetic"
    RECORDED = "recorded"
    LIVE = "live"


class DataDomain(StrEnum):
    AIS = "ais"
    WEATHER_TIDE = "weather_tide"
    BERTH_PLAN = "berth_plan"
    SERVICE_CALIBRATION = "service_calibration"


class AdapterHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    STALE = "stale"
    OFFLINE = "offline"
    UNCONFIGURED = "unconfigured"
    ERROR = "error"


class DataSourceProvenance(BaseModel):
    source_id: str
    domain: DataDomain
    mode: DataSourceMode
    provider: str
    observed_at: datetime
    received_at: datetime
    freshness_seconds: int = 0
    stale_after_seconds: int = 300
    stale: bool = False
    health: AdapterHealth = AdapterHealth.HEALTHY
    record_count: int = 0
    detail: str | None = None
    last_success_at: datetime | None = None
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    retry_delay_seconds: int = 0
    consecutive_errors: int = 0
    using_cached_records: bool = False


class AdapterSnapshot(BaseModel):
    adapter_id: str
    provenance: DataSourceProvenance
    records: list[dict] = Field(default_factory=list)


class OperatorIdentity(BaseModel):
    operator_id: str
    display_name: str
    role: OperatorRole


class IntegrationIdentity(BaseModel):
    integration_id: str
    display_name: str
    vessel_ids: list[str] = Field(min_length=1)


class VesselRuntimeEvent(BaseModel):
    contract_version: Literal["portflow.vessel-event.v1"] = "portflow.vessel-event.v1"
    event_id: str = Field(min_length=8, max_length=96)
    occurred_at: datetime
    vessel_id: str = Field(min_length=1, max_length=80)
    port_call_id: str | None = Field(default=None, max_length=80)
    event_type: VesselRuntimeEventType
    sequence: int = Field(ge=0)
    source_system: str = Field(min_length=1, max_length=120)
    payload: dict[str, object] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_event_time(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return self


class VesselRuntimeEventReceipt(BaseModel):
    contract_version: Literal["portflow.vessel-event-receipt.v1"] = (
        "portflow.vessel-event-receipt.v1"
    )
    event_id: str
    accepted_at: datetime
    duplicate: bool = False


class VesselRuntimeEventRecord(BaseModel):
    event: VesselRuntimeEvent
    integration_id: str
    received_at: datetime


class VesselOperationalExceptionHistoryItem(BaseModel):
    state: Literal[
        "open",
        "acknowledged",
        "claimed",
        "escalated",
        "released",
        "override_recorded",
        "resolved",
    ]
    source_sequence: int = Field(ge=0)
    occurred_at: datetime


class VesselOperationalException(BaseModel):
    vessel_id: str
    port_call_id: str | None = None
    exception_ref: str = Field(
        min_length=34,
        max_length=34,
        pattern=r"^mrt-exception-[0-9a-f]{20}$",
    )
    state: Literal[
        "open",
        "acknowledged",
        "claimed",
        "escalated",
        "released",
        "override_recorded",
        "resolved",
    ]
    risk: RiskLevel
    title: str
    summary: str
    first_source_sequence: int = Field(ge=0)
    latest_source_sequence: int = Field(ge=0)
    opened_at: datetime
    updated_at: datetime
    opened_event_id: str
    latest_event_id: str
    lifecycle_event_count: int = Field(ge=1)
    history: list[VesselOperationalExceptionHistoryItem] = Field(
        default_factory=list,
        max_length=64,
    )
    privacy_minimized: Literal[True] = True
    advisory_only: Literal[True] = True
    execution_authorized: Literal[False] = False


class ScenarioAction(BaseModel):
    action_type: ScenarioActionType
    incident_type: IncidentType | None = None
    link_mode: LinkMode | None = None
    target_port_call_id: str | None = None
    impact_minutes: int | None = None


class ScenarioFixture(BaseModel):
    id: str
    title: str
    description: str
    actions: list[ScenarioAction]


class Coordinate(BaseModel):
    lat: float
    lon: float


class Vessel(BaseModel):
    id: str
    source_id: str = "synthetic-ais"
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
    source_id: str = "synthetic-berth-plan"
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
    source_id: str = "synthetic-berth-plan"
    vessel_id: str
    berth_id: str
    arrival_eta: datetime
    departure_eta: datetime
    stages: list[PortCallStage]
    delay_minutes: int = 0
    risk: RiskLevel = RiskLevel.LOW
    estimated_cost_exposure_usd: float = 0


class WeatherState(BaseModel):
    source_id: str = "synthetic-weather"
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


class Incident(BaseModel):
    id: str
    incident_type: IncidentType
    status: IncidentStatus = IncidentStatus.ACTIVE
    severity: RiskLevel
    title: str
    started_at: datetime
    target_port_call_id: str | None = None
    target_berth_id: str | None = None
    target_resource_id: str | None = None
    impact_minutes: int = 0
    details: str
    resolved_at: datetime | None = None




class ResourceUnavailableWindow(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str = "unavailable"

    @model_validator(mode="after")
    def validate_window(self):
        if self.end_at <= self.start_at:
            raise ValueError("Resource unavailable window end_at must be after start_at")
        return self


class ServiceResource(BaseModel):
    id: str
    kind: ServiceKind
    name: str
    status: ResourceStatus = ResourceStatus.AVAILABLE
    capacity: int = 1
    assigned_port_call_ids: list[str] = Field(default_factory=list)
    available_from: datetime | None = None
    unavailable_windows: list[ResourceUnavailableWindow] = Field(default_factory=list)


class ServiceStep(BaseModel):
    id: str
    port_call_id: str
    kind: ServiceKind
    label: str
    planned_at: datetime
    duration_minutes: int = Field(default=0, ge=0, le=24 * 60)
    state: ServiceState = ServiceState.READY
    resource_id: str | None = None
    dependency_step_ids: list[str] = Field(default_factory=list)




class ServiceDurationCalibration(BaseModel):
    service_kind: ServiceKind
    duration_minutes: int = Field(ge=1, le=24 * 60)
    source_id: str
    mode: DataSourceMode
    provider: str
    observed_at: datetime
    detail: str | None = None


class RecoveryAction(BaseModel):
    action_type: RecoveryActionType
    port_call_id: str
    service_kind: ServiceKind | None = None
    from_resource_id: str | None = None
    to_resource_id: str | None = None
    from_berth_id: str | None = None
    to_berth_id: str | None = None
    shift_minutes: int = 0


class RecoveryProposal(BaseModel):
    id: str
    state_fingerprint: str
    title: str
    target_port_call_id: str
    incident_id: str | None = None
    incident_ids: list[str] = Field(default_factory=list)
    actions: list[RecoveryAction]
    projected_total_delay_minutes: int
    projected_modeled_cost_usd: float
    projected_berth_conflicts: int
    projected_blocked_services: int
    projected_risk: RiskLevel
    disruption_score: float
    decision_confidence: DecisionConfidence
    data_quality_warnings: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    requires_approval: bool = True


class RecoveryProposalEvidenceBatch(BaseModel):
    evidence_id: str
    generated_at: datetime
    requested_call_id: str | None = None
    trigger: str = "planning"
    stale_parent_proposal_id: str | None = None
    proposals: list[RecoveryProposal] = Field(default_factory=list)


class RecoveryContingency(BaseModel):
    stale_proposal_id: str
    target_port_call_id: str
    stale_state_fingerprint: str
    current_state_fingerprint: str
    unavailable_resource_ids: list[str] = Field(default_factory=list)
    replacement_proposals: list[RecoveryProposal] = Field(default_factory=list)
    reason: str
    auto_apply: bool = False


class VesselCoordinationSnapshot(BaseModel):
    contract_version: Literal["portflow.coordination.v1"] = "portflow.coordination.v1"
    generated_at: datetime
    port_call_id: str
    vessel_id: str
    berth_id: str
    arrival_eta: datetime
    departure_eta: datetime
    delay_minutes: int
    risk: RiskLevel
    stages: list[PortCallStage] = Field(default_factory=list)
    service_steps: list[ServiceStep] = Field(default_factory=list)
    active_incidents: list[Incident] = Field(default_factory=list)
    recovery_proposals: list[RecoveryProposal] = Field(default_factory=list)
    advisory_only: bool = True
    requires_human_approval: bool = True
    actuation_allowed: bool = False


class RecoveryApplicationReceipt(BaseModel):
    proposal_id: str
    state_fingerprint: str = "legacy"
    applied_at: datetime
    target_port_call_id: str
    incident_ids: list[str] = Field(default_factory=list)
    actions: list[RecoveryAction]
    resulting_berth_conflicts: int
    resulting_blocked_services: int
    resulting_total_delay_minutes: int
    resulting_modeled_cost_usd: float
    approved_by: str = "legacy_operator"
    approved_role: OperatorRole = OperatorRole.OPERATOR
    approved_display_name: str | None = None


class ReplayReceipt(BaseModel):
    envelope_id: str
    event_id: str
    replayed_at: datetime
    delivery_status: str
    attempts: int


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
    incident_id: str | None = None
    actor_id: str | None = None
    actor_role: OperatorRole | None = None
    source_id: str | None = None


class HarborOverview(BaseModel):
    generated_at: datetime
    # Additive UI invalidation key, not an authorization token or evidence hash.
    # Omit when absent in old records so their byte-level evidence digests survive.
    decision_revision: str = Field(default='', exclude_if=lambda value: not value)
    port_name: str
    center: Coordinate
    vessels: list[Vessel]
    berths: list[Berth]
    port_calls: list[PortCall]
    weather: WeatherState
    connectivity: ConnectivityState
    incidents: list[Incident] = Field(default_factory=list)
    service_resources: list[ServiceResource] = Field(default_factory=list)
    service_steps: list[ServiceStep] = Field(default_factory=list)
    service_duration_calibrations: list[ServiceDurationCalibration] = Field(default_factory=list)
    events: list[OperationsEvent]
    data_sources: list[DataSourceProvenance] = Field(default_factory=list)
    metrics: dict[str, float | int]
    data_disclaimer: str


class ScenarioRunEvidence(BaseModel):
    run_id: str
    ran_at: datetime
    scenario: ScenarioFixture
    harbor: HarborOverview
    recovery_proposals: list[RecoveryProposal] = Field(default_factory=list)
