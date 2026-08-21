from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from database.models import ActivitySource, ActivityStatus, ActivityType, AgreementKind


class WorkSchedule(BaseModel):
    """Timefordeling: 7 værdier (man-søn) for lige og ulige uger."""
    even: list[Annotated[float, Field(ge=0, le=24)]] = Field(
        default_factory=lambda: [0.0] * 7, min_length=7, max_length=7
    )
    odd: list[Annotated[float, Field(ge=0, le=24)]] = Field(
        default_factory=lambda: [0.0] * 7, min_length=7, max_length=7
    )


class DispatcherGroupResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    visible_in_activity_overview: bool = True

    model_config = {"from_attributes": True}


class EmployeeCreate(BaseModel):
    employee_number: str                       # Lønnummer
    tachograph_card_number: Optional[str] = None  # Førerkortnummer
    first_name: str
    last_name: str
    address: Optional[str] = None
    postal_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    agreement_kind: AgreementKind = AgreementKind.hourly_fixed
    agreement_type: str                        # Overenskomsttype fra Excel-ark
    fuldloennet: bool = True
    active: bool = True
    hire_date: date
    termination_date: date = date(9999, 12, 31)
    work_schedule: WorkSchedule = Field(default_factory=WorkSchedule)
    dispatcher_group_ids: list[int] = Field(default_factory=list)
    cvr_number: Optional[str] = None
    initials: Optional[str] = None


class EmployeeUpdate(BaseModel):
    employee_number: Optional[str] = None
    tachograph_card_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address: Optional[str] = None
    postal_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    agreement_kind: Optional[AgreementKind] = None
    agreement_type: Optional[str] = None
    fuldloennet: Optional[bool] = None
    active: Optional[bool] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    work_schedule: Optional[WorkSchedule] = None
    dispatcher_group_ids: Optional[list[int]] = None
    cvr_number: Optional[str] = None
    initials: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_number: str
    tachograph_card_number: Optional[str]
    first_name: str
    last_name: str
    name: str
    address: Optional[str]
    postal_code: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    mobile: Optional[str]
    agreement_kind: AgreementKind
    agreement_type: str
    hourly_rate: Optional[float]
    fuldloennet: bool
    active: bool
    hire_date: date
    termination_date: date
    work_schedule: WorkSchedule
    months_employed: int
    dispatcher_groups: list[DispatcherGroupResponse] = Field(default_factory=list)
    cvr_number: Optional[str] = None
    anciennitet_dismissed_at: Optional[datetime] = None
    terminsdato: Optional[date] = None
    initials: Optional[str] = None

    model_config = {"from_attributes": True}


class ActivityResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_number: str
    pay_period_id: int
    source: ActivitySource
    activity_type: str
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    availability_time_pct: Optional[Decimal]
    rest_pause_pct: Optional[Decimal]
    other_work_pct: Optional[Decimal]
    driving_pct: Optional[Decimal]
    loading_minutes: Optional[int]
    unloading_minutes: Optional[int]
    pause_intervals: list[list[str]] = []
    segments: list[list[str]] = []
    is_edited: bool = False
    has_split_children: bool = False
    parent_activity_id: Optional[int] = None
    status: ActivityStatus
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    deactivated_by: Optional[str] = None
    comment: Optional[str]
    is_under_4h: bool
    is_over_12h: bool
    is_manual: bool
    created_by: Optional[str] = None
    vehicle_registration: Optional[str] = None
    vehicle_number: Optional[str] = None
    km_start: Optional[int] = None
    km_end: Optional[int] = None
    salt_supplement: bool = False
    auto_approved: bool = False
    auto_approval_flags: list[str] = []
    is_likely_incomplete: bool = False


class ActivityCreate(BaseModel):
    employee_id: int
    activity_type: str = "normal"
    start_time: datetime
    end_time: datetime
    loading_minutes: Optional[int] = Field(default=None, ge=0)
    unloading_minutes: Optional[int] = Field(default=None, ge=0)
    comment: Optional[str] = Field(default=None, max_length=1000)
    vehicle_number: Optional[str] = Field(default=None, max_length=50)
    km_start: Optional[int] = Field(default=None, ge=0)
    km_end: Optional[int] = Field(default=None, ge=0)
    salt_supplement: bool = False
    terminsdato: Optional[date] = None
    pause_intervals: list = Field(default_factory=list)

    @model_validator(mode="after")
    def end_after_start(self):
        if self.activity_type in ("overnatning", "dob_overnatning"):
            return self
        if self.end_time <= self.start_time:
            raise ValueError("Sluttid skal være efter starttid")
        return self

    @model_validator(mode="after")
    def km_end_ge_start(self):
        if self.km_start is not None and self.km_end is not None and self.km_end < self.km_start:
            raise ValueError("km_end skal være større end eller lig med km_start")
        return self

    @model_validator(mode="after")
    def pauses_within_activity(self):
        for p in (self.pause_intervals or []):
            try:
                ps = datetime.fromisoformat(p[0]) if isinstance(p[0], str) else p[0]
                pe = datetime.fromisoformat(p[1]) if isinstance(p[1], str) else p[1]
            except (ValueError, IndexError, TypeError):
                continue
            if ps < self.start_time:
                raise ValueError(
                    f"Pause ({ps.strftime('%H:%M')}) starter før aktiviteten begynder ({self.start_time.strftime('%H:%M')})"
                )
            if pe > self.end_time:
                raise ValueError(
                    f"Pause ({pe.strftime('%H:%M')}) slutter efter aktiviteten er slut ({self.end_time.strftime('%H:%M')})"
                )
        return self


class ActivityUpdate(BaseModel):
    activity_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    loading_minutes: Optional[int] = Field(default=None, ge=0)
    unloading_minutes: Optional[int] = Field(default=None, ge=0)
    comment: Optional[str] = Field(default=None, max_length=1000)
    vehicle_number: Optional[str] = Field(default=None, max_length=50)
    km_start: Optional[int] = Field(default=None, ge=0)
    km_end: Optional[int] = Field(default=None, ge=0)
    salt_supplement: Optional[bool] = None
    pause_intervals: Optional[list] = None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.activity_type in ("overnatning", "dob_overnatning"):
            return self
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("Sluttid skal være efter starttid")
        return self


class ActivityApprove(BaseModel):
    comment: Optional[str] = None


class ActivityDeactivate(BaseModel):
    comment: Optional[str] = None


class ActivitySplit(BaseModel):
    split_at: datetime


class AnciennitetsAlert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    hire_date: date
    months_employed: int
    suggested_agreement_type: Optional[str] = None


class VehicleCreate(BaseModel):
    registration_number: str
    vehicle_number: str


class VehicleUpdate(BaseModel):
    registration_number: Optional[str] = None
    vehicle_number: Optional[str] = None


class VehicleResponse(BaseModel):
    id: int
    registration_number: str
    vehicle_number: str

    model_config = {"from_attributes": True}


class EmployeeSupplementCreate(BaseModel):
    employee_id: int
    start_date: date = Field(default_factory=date.today)
    value: Annotated[float, Field(gt=0, le=10000)]


class EmployeeSupplementResponse(BaseModel):
    id: int
    employee_id: int
    employee_number: str
    employee_name: str
    name: str
    type: str
    value: float
    start_date: date
    end_date: date
    is_active: bool

    model_config = {"from_attributes": True}
