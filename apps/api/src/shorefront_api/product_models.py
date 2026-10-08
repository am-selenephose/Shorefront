"""Validated customer facts. No fixtures, inferred observations or simulator defaults."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')]
Label = Annotated[str, Field(min_length=1, max_length=200)]


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Port(StrictModel):
    name: Label
    timezone: str = Field(max_length=80)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('Use an IANA timezone, for example Asia/Karachi') from exc
        return value


class Berth(StrictModel):
    name: Label
    port_id: Identifier
    max_length_m: float | None = Field(default=None, gt=0, le=2000, allow_inf_nan=False)
    max_draft_m: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


class Vessel(StrictModel):
    name: Label
    imo: str | None = Field(default=None, pattern=r'^\d{7}$')
    length_m: float | None = Field(default=None, gt=0, le=2000, allow_inf_nan=False)
    draft_m: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)


class Call(StrictModel):
    vessel_id: Identifier
    berth_id: Identifier | None = None
    eta: AwareDatetime
    etd: AwareDatetime
    status: Literal['planned', 'arrived', 'berthed', 'departed', 'cancelled'] = 'planned'

    @model_validator(mode='after')
    def times_ordered(self):
        if self.etd <= self.eta:
            raise ValueError('Departure must be after arrival')
        return self


class Resource(StrictModel):
    name: Label
    port_id: Identifier
    resource_type: Literal['tug', 'pilot', 'crew', 'equipment']
    available: bool


class ResourceAssignment(StrictModel):
    # An explicit time-bounded connection between a *specific* port call and
    # a resource. Port-wide availability by itself never implies assignment.
    call_id: Identifier
    resource_id: Identifier
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    status: Literal['proposed', 'confirmed', 'released'] = 'proposed'
    confirmation_note: str = Field(default='', max_length=2000)
    release_note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def verify_assignment(self):
        if self.ends_at <= self.starts_at:
            raise ValueError('Resource assignment ends_at must follow starts_at')
        if self.status == 'confirmed' and not self.confirmation_note.strip():
            raise ValueError('Confirmed resource assignment requires a named confirmation note')
        if self.status == 'released' and not self.release_note.strip():
            raise ValueError('Released resource assignment requires a release note')
        return self


class Incident(StrictModel):
    title: Label
    call_id: Identifier | None = None
    severity: Literal['low', 'medium', 'high', 'critical'] = 'medium'
    status: Literal['open', 'acknowledged', 'resolved'] = 'open'
    detail: str = Field(default='', max_length=4000)


class Task(StrictModel):
    title: Label
    call_id: Identifier | None = None
    incident_id: Identifier | None = None
    assignee_id: Identifier | None = None
    due_at: AwareDatetime
    status: Literal['open', 'in_progress', 'done'] = 'open'
    completion_note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def completion_evidence(self):
        if self.status == 'done' and not self.completion_note:
            raise ValueError('A completed task needs a completion note')
        return self


class Coordination(StrictModel):
    title: Label
    call_id: Identifier
    recipient_id: Identifier
    due_at: AwareDatetime
    note: str = Field(default='', max_length=4000)
    proof: str = Field(default='', max_length=2000)


class Handoff(Coordination):
    status: Literal['prepared', 'sent', 'acknowledged'] = 'prepared'

    @model_validator(mode='after')
    def receipt_proof(self):
        if self.status == 'acknowledged' and not self.proof:
            raise ValueError('Acknowledgement requires recipient confirmation')
        return self


class Commitment(Coordination):
    status: Literal['proposed', 'accepted', 'declined', 'fulfilled', 'cancelled'] = 'proposed'

    @model_validator(mode='after')
    def fulfillment_proof(self):
        if self.status == 'fulfilled' and not self.proof:
            raise ValueError('Fulfillment requires completion evidence')
        return self


class Obligation(StrictModel):
    title: Label
    call_id: Identifier
    assignee_id: Identifier
    due_at: AwareDatetime
    clause_reference: str = Field(min_length=1, max_length=1000)
    status: Literal['draft', 'active', 'completed', 'cancelled'] = 'draft'
    review_note: str = Field(default='', max_length=2000)
    proof: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def reviewed_evidence(self):
        if self.status in {'active', 'completed'} and not self.review_note:
            raise ValueError('An active obligation requires a human review note')
        if self.status == 'completed' and not self.proof:
            raise ValueError('Completion requires documentary evidence')
        return self


class Outcome(StrictModel):
    decision_id: Identifier
    actual_arrival: AwareDatetime
    actual_departure: AwareDatetime
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def actual_times(self):
        if self.actual_departure <= self.actual_arrival:
            raise ValueError('Actual departure must be after actual arrival')
        if self.actual_departure > now():
            raise ValueError('A future event is not an observed outcome')
        return self


RECORD_MODELS = {'port': Port, 'berth': Berth, 'vessel': Vessel, 'call': Call,
                 'resource': Resource, 'resource_assignment': ResourceAssignment,
                 'incident': Incident, 'task': Task,
                 'handoff': Handoff, 'commitment': Commitment, 'obligation': Obligation, 'outcome': Outcome}
REFERENCES = {'port_id': 'port', 'berth_id': 'berth', 'vessel_id': 'vessel',
              'call_id': 'call', 'resource_id': 'resource',
              'incident_id': 'incident'}


class RecordCommand(StrictModel):
    record_id: Identifier
    expected_revision: int = Field(ge=0)
    valid_at: AwareDatetime | None = None
    source: str = Field(min_length=1, max_length=500)
    payload: dict


class Login(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().casefold()
        if value.count('@') != 1 or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address')
        local, domain = value.split('@')
        if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
            raise ValueError('Enter a valid email address')
        return value


class Signup(Login):
    display_name: Label
    password: str = Field(min_length=15, max_length=128)


class Bootstrap(Signup):
    bootstrap_token: str = Field(min_length=1, max_length=256)


class AcceptInvite(Signup):
    invitation_token: str = Field(min_length=1, max_length=256)


class Invitation(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    role: Literal['admin', 'operator', 'supervisor', 'viewer']

    _email = field_validator('email')(Login.normalize_email.__func__)


class PasswordChange(StrictModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class ConflictResolution(StrictModel):
    accepted_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


class ImportItem(StrictModel):
    kind: Identifier
    command: RecordCommand


class ImportBatch(StrictModel):
    records: list[ImportItem] = Field(min_length=1, max_length=100)


class ProposedPlan(StrictModel):
    berth_id: Identifier | None
    eta: AwareDatetime
    etd: AwareDatetime

    @model_validator(mode='after')
    def valid_window(self):
        if self.etd <= self.eta:
            raise ValueError('Proposed departure must be after arrival')
        return self


class DecisionRequest(StrictModel):
    call_id: Identifier
    question: str = Field(min_length=1, max_length=1000)
    proposed: ProposedPlan | None = None


class ApprovalRequest(StrictModel):
    option_id: Identifier
    reason: str = Field(min_length=1, max_length=2000)


INGESTIBLE_KINDS = {'port', 'berth', 'vessel', 'call', 'resource', 'resource_assignment', 'incident', 'task', 'outcome'}
PROJECTABLE_KINDS = set(RECORD_MODELS)
SUPPORTED_STANDARD_PROFILES = {'dcsa-port-call-2.0.0'}


class SourceCreate(StrictModel):
    id: Identifier
    name: Label
    allowed_kinds: list[str] = Field(min_length=1, max_length=20)
    standard_profiles: list[str] = Field(default_factory=list, max_length=20)
    expires_in_hours: int = Field(default=720, ge=1, le=8760)

    @field_validator('allowed_kinds')
    @classmethod
    def valid_ingest_kinds(cls, values):
        if len(values) != len(set(values)) or any(value not in INGESTIBLE_KINDS for value in values):
            raise ValueError('Sources may write only explicitly supported operational record kinds')
        return values

    @field_validator('standard_profiles')
    @classmethod
    def valid_standard_profiles(cls, values):
        if len(values) != len(set(values)) or any(value not in SUPPORTED_STANDARD_PROFILES for value in values):
            raise ValueError('Unsupported operational standard profile')
        return values


class IntegrationItem(StrictModel):
    kind: str
    record_id: Identifier
    expected_revision: int = Field(ge=0)
    valid_at: AwareDatetime | None = None
    payload: dict

    @field_validator('kind')
    @classmethod
    def valid_kind(cls, value):
        if value not in INGESTIBLE_KINDS:
            raise ValueError('Unsupported integration record kind')
        return value


class IntegrationBatch(StrictModel):
    records: list[IntegrationItem] = Field(min_length=1, max_length=100)


class PartnerDeliveryAck(StrictModel):
    payload_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    note: str = Field(default='', max_length=1000)


class PartnerGrantCreate(StrictModel):
    id: Identifier
    name: Label
    allowed_kinds: list[str] = Field(min_length=1, max_length=20)
    fields: dict[str, list[str]]
    call_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    expires_in_hours: int = Field(default=24, ge=1, le=2160)

    @model_validator(mode='after')
    def validate_projection(self):
        if len(self.allowed_kinds) != len(set(self.allowed_kinds)) or any(kind not in PROJECTABLE_KINDS for kind in self.allowed_kinds):
            raise ValueError('Projection contains an unsupported record kind')
        if set(self.fields) != set(self.allowed_kinds):
            raise ValueError('Every projected kind needs an explicit field allowlist')
        for kind, fields in self.fields.items():
            if not fields or len(fields) != len(set(fields)):
                raise ValueError(f'{kind} requires a non-empty unique field allowlist')
            allowed = set(RECORD_MODELS[kind].model_fields)
            unknown = set(fields) - allowed
            if unknown:
                raise ValueError(f'{kind} projection contains unknown fields: {", ".join(sorted(unknown))}')
        return self
