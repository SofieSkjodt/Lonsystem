from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Numeric,
    ForeignKey, Text, Enum, JSON, Index, UniqueConstraint, text
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum
from datetime import date


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    lonbogholder = "lonbogholder"
    disponent = "disponent"


class AgreementKind(str, enum.Enum):
    """Aftale: timelønnet med fast eller ikke fastlagt arbejdstid."""
    hourly_fixed = "hourly_fixed"          # Timelønnet, fast arbejdstid
    hourly_flexible = "hourly_flexible"    # Timelønnet, ikke fastlagt arbejdstid


class ActivitySource(str, enum.Enum):
    tachograph = "tachograph"
    manual = "manual"
    vagtplan = "vagtplan"


class ActivityType(str, enum.Enum):
    normal = "normal"
    ferie = "ferie"
    fri = "fri"
    afspadsering = "afspadsering"
    skole_kursus = "skole_kursus"


class ActivityStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    deactivated = "deactivated"


class PayPeriodStatus(str, enum.Enum):
    open = "open"
    preview = "preview"
    closed = "closed"


# Default timefordeling: ingen timer (skal udfyldes ved oprettelse)
def default_work_schedule():
    return {"even": [0, 0, 0, 0, 0, 0, 0], "odd": [0, 0, 0, 0, 0, 0, 0]}


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    employee_number = Column(String, unique=True, nullable=False)   # Lønnummer
    tachograph_card_number = Column(String, unique=True, nullable=True)  # Førerkortnummer
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    initials = Column(String(10), nullable=True)  # matcher app_users.initials for "egen linje"-rettighed i Vagtplan
    # Nøgle fra master_agreement_kinds.key – ikke længere en hård enum-kolonne,
    # da nye Aftale-typer kan tilføjes via Stamdata (se AgreementKind for de to
    # systemnøgler, som overtidsberegningen fortsat kender).
    agreement_kind = Column(String(50), nullable=False, default="hourly_fixed")
    agreement_type = Column(String, nullable=False)  # Overenskomsttype fra Excel-arket
    fuldloennet = Column(Boolean, default=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    hire_date = Column(Date, nullable=False)
    termination_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    # Timefordeling over 14 dage: {"even": [man..søn], "odd": [man..søn]} i timer
    work_schedule = Column(JSON, nullable=False, default=default_work_schedule)
    cvr_number = Column(String(20), nullable=True)          # Tilknyttet CVR-nummer (None = standard)
    anciennitet_dismissed_at = Column(DateTime, nullable=True)  # Tidspunkt for afvist anciennitetsadvarsel
    terminsdato = Column(Date, nullable=True)  # Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet
    paragraf_56 = Column(Boolean, default=False, nullable=False)
    paragraf_56_start_date = Column(Date, nullable=True)
    paragraf_56_end_date = Column(Date, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    activities = relationship("Activity", back_populates="employee")
    baselines = relationship("EmployeeBaseline", back_populates="employee")
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    dispatcher_group = relationship("DispatcherGroup", back_populates="employees")

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Paragraf56AlertDismissal(Base):
    __tablename__ = "paragraf_56_alert_dismissals"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)  # "upcoming" | "expired"
    dismissed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "user_id", "alert_type", name="uq_paragraf56_dismissal"),
    )


class PayPeriod(Base):
    __tablename__ = "pay_periods"

    id = Column(Integer, primary_key=True)
    start_date = Column(Date, nullable=False, unique=True)
    end_date = Column(Date, nullable=False)
    status = Column(Enum(PayPeriodStatus), default=PayPeriodStatus.open, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String, nullable=True)

    activities = relationship("Activity", back_populates="pay_period")
    payroll_runs = relationship("PayrollRun", back_populates="pay_period")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    trip_number = Column(String(6), nullable=True)
    source = Column(Enum(ActivitySource), nullable=False)
    activity_type = Column(String(50), default="normal", nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    availability_time_pct = Column(Numeric(5, 2), nullable=True)
    rest_pause_pct = Column(Numeric(5, 2), nullable=True)
    other_work_pct = Column(Numeric(5, 2), nullable=True)
    driving_pct = Column(Numeric(5, 2), nullable=True)
    loading_minutes = Column(Integer, nullable=True)
    unloading_minutes = Column(Integer, nullable=True)
    # Pauseintervaller [["ISO-start","ISO-slut"], ...] – pauser fratrækkes
    # i det tidsrum de afholdes (vigtigt for korrekt tillægsberegning)
    pause_intervals = Column(JSON, nullable=False, default=list)
    # Alle hændelsessegmenter fra tachografen:
    # [["ISO-start","ISO-slut","rest|availability|work|driving"], ...]
    segments = Column(JSON, nullable=False, default=list)
    created_by = Column(String, nullable=True)   # initialer på bruger der oprettede manuelt
    # Originale tider gemmes ved første manuelle rettelse (muliggør fortryd)
    original_start_time = Column(DateTime, nullable=True)
    original_end_time = Column(DateTime, nullable=True)
    status = Column(Enum(ActivityStatus), default=ActivityStatus.pending, nullable=False)
    approved_by = Column(String, nullable=True)     # initialer – sat ved godkendelse
    approved_at = Column(DateTime, nullable=True)
    deactivated_by = Column(String, nullable=True)  # initialer – sat ved deaktivering
    comment = Column(Text, nullable=True)
    parent_activity_id = Column(Integer, ForeignKey("activities.id"), nullable=True)
    split_part = Column(Integer, nullable=True)
    vehicle_registration = Column(String, nullable=True)
    vehicle_number = Column(String, nullable=True)
    km_start = Column(Integer, nullable=True)
    km_end = Column(Integer, nullable=True)
    salt_supplement = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    auto_approved = Column(Boolean, default=False, nullable=False, server_default="0")
    auto_approval_flags = Column(JSON, nullable=False, default=list, server_default='[]')
    is_likely_incomplete = Column(Boolean, default=False, nullable=False, server_default="0")
    hidden_from_vagtplan = Column(Boolean, default=False, nullable=False, server_default="0")
    baseline_duration_minutes = Column(Numeric(10, 4), nullable=True)
    baseline_start_hour = Column(Numeric(8, 4), nullable=True)

    employee = relationship("Employee", back_populates="activities")
    pay_period = relationship("PayPeriod", back_populates="activities")
    split_children = relationship("Activity", foreign_keys=[parent_activity_id])

    __table_args__ = (
        # Bruges af duplikat-tjek ved ddd-import (employee_id + start_time + source).
        # Uden dette index scanner SQLite hele tabellen for hver importeret aktivitet.
        Index("ix_activities_employee_start_source", "employee_id", "start_time", "source"),
    )


class DispatcherGroup(Base):
    __tablename__ = "dispatcher_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    visible_in_activity_overview = Column(Boolean, nullable=False, default=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)

    employees = relationship("Employee", back_populates="dispatcher_group")
    vehicle = relationship("Vehicle")

    @property
    def vehicle_number(self) -> str | None:
        return self.vehicle.vehicle_number if self.vehicle else None


class VagtplanComment(Base):
    __tablename__ = "vagtplan_comments"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(Date, nullable=False)
    text = Column(String(1000), nullable=False)
    created_by = Column(String(10), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_vagtplan_comments_employee_date"),
    )


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id = Column(Integer, primary_key=True)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    run_type = Column(String, nullable=False)  # "preview" or "final"
    run_at = Column(DateTime, server_default=func.now())
    run_by = Column(String, nullable=True)
    csv_path = Column(String, nullable=True)
    excel_path = Column(String, nullable=True)

    pay_period = relationship("PayPeriod", back_populates="payroll_runs")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    registration_number = Column(String, unique=True, nullable=False)  # Registreringsnummer (nummerplade)
    vehicle_number = Column(String, nullable=False)                     # Vognnummer
    created_at = Column(DateTime, server_default=func.now())


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)          # fx "admin", "lonbogholder"
    display_name = Column(String, nullable=False)               # fx "Administrator"
    is_system = Column(Boolean, default=False, nullable=False)  # systemroller kan ikke slettes
    permissions = Column(JSON, nullable=False, default=list)    # ["payroll","import_ddd",...]


class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    initials = Column(String(10), unique=True, nullable=False)
    email = Column(String, nullable=True)
    role = Column(String, nullable=False)   # navn på en rolle i roles-tabellen
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=True)
    user_initials = Column(String(10), nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)


class MasterAgreementType(Base):
    __tablename__ = "master_agreement_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)


class MasterAgreementKind(Base):
    __tablename__ = "master_agreement_kinds"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    requires_agreement_type = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


class MasterCvrNumber(Base):
    __tablename__ = "master_cvr_numbers"

    id = Column(Integer, primary_key=True)
    cvr_number = Column(String(20), unique=True, nullable=False)
    company_name = Column(String(200), nullable=False, default="")
    is_default = Column(Boolean, default=False, nullable=False)


class MasterOvertimeRate(Base):
    __tablename__ = "master_overtime_rates"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), unique=True, nullable=False)
    rate = Column(Numeric(10, 4), nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterSupplementRate(Base):
    __tablename__ = "master_supplement_rates"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), unique=True, nullable=False)
    rate = Column(Numeric(10, 4), nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterPayType(Base):
    __tablename__ = "master_pay_types"

    id = Column(Integer, primary_key=True)
    code_key = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    danloen_code = Column(String(50), nullable=False, default="")
    include_in_csv = Column(Boolean, default=True, nullable=False)
    csv_quantity_type = Column(String(20), nullable=False, default="hours", server_default="hours")
    csv_rate_source = Column(String(30), nullable=False, default="hourly", server_default="hourly")
    csv_include_rate = Column(Boolean, default=True, nullable=False, server_default="1")
    csv_include_total = Column(Boolean, default=False, nullable=False, server_default="0")
    sort_order = Column(Integer, default=0, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterAbsenceType(Base):
    __tablename__ = "master_absence_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=False)
    normalized_key = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


class Holiday(Base):
    __tablename__ = "holidays"

    id                = Column(Integer, primary_key=True)
    date              = Column(Date, unique=True, nullable=False)
    name              = Column(String(200), nullable=False)
    half_day_from     = Column(String(5), nullable=True)    # "12:00" = fri fra middag; NULL = heldagshelligdag
    is_auto_generated = Column(Boolean, default=True, nullable=False)


class DeclinedImport(Base):
    """Vagte en bruger eksplicit har valgt IKKE at importere (fx en vagt i en
    allerede lukket lønperiode) – huskes så de ikke bliver foreslået igen ved
    en senere genimport af samme .ddd-fil."""
    __tablename__ = "declined_imports"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    declined_by = Column(String, nullable=True)
    declined_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_declined_imports_employee_start", "employee_id", "start_time", unique=True),
    )


class EmployeeBaseline(Base):
    __tablename__ = "employee_baselines"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    weekday = Column(Integer, nullable=False)          # 0=mandag … 6=søndag
    sample_count = Column(Integer, default=0, nullable=False)
    duration_mean_minutes = Column(Numeric(10, 4), default=0, nullable=False)
    duration_m2_minutes = Column(Numeric(14, 6), default=0, nullable=False)  # Welford M2
    start_hour_mean = Column(Numeric(8, 4), default=0, nullable=False)       # float timer, fx 7.5 = 07:30
    start_hour_m2 = Column(Numeric(12, 6), default=0, nullable=False)        # Welford M2
    salt_count = Column(Integer, default=0, nullable=False)                  # antal aktiviteter med salt
    last_updated = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="baselines")


class EmployeeSupplement(Base):
    __tablename__ = "employee_supplements"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="Ikke overenskomstmæssigt tillæg")
    type = Column(String(50), nullable=False, default="Timebaseret")
    value = Column(Numeric(10, 2), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")

    __table_args__ = (
        Index(
            "uq_employee_supplements_one_open_row",
            "employee_id",
            unique=True,
            sqlite_where=text("end_date = '9999-12-31'"),
        ),
    )


class EmployeeSpringerFlag(Base):
    __tablename__ = "employee_springer_flags"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False, index=True)
    enabled = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)

    employee = relationship("Employee")
    pay_period = relationship("PayPeriod")

    __table_args__ = (
        Index("uq_employee_springer_flags_emp_period", "employee_id", "pay_period_id", unique=True),
    )
