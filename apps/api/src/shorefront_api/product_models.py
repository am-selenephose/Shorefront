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
                 'resource': Resource, 'incident': Incident, 'task': Task,
                 'handoff': Handoff, 'commitment': Commitment, 'obligation': Obligation, 'outcome': Outcome}
REFERENCES = {'port_id': 'port', 'berth_id': 'berth', 'vessel_id': 'vessel',
              'call_id': 'call', 'incident_id': 'incident'}


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


class ImportItem(StrictModel):
    kind: Identifier
    command: RecordCommand


class ImportBatch(StrictModel):
    records: list[ImportItem] = Field(min_length=1, max_length=100)


class DecisionRequest(StrictModel):
    call_id: Identifier
    question: str = Field(min_length=1, max_length=1000)


class ApprovalRequest(StrictModel):
    option_id: Identifier
    reason: str = Field(min_length=1, max_length=2000)
