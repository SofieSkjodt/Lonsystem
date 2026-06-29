from datetime import datetime

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline


def update_baseline_from_activity(activity: Activity, db: Session) -> None:
    """Opdaterer EmployeeBaseline for aktivitetens medarbejder+ugedag via Welford's algoritme.
    Ignorerer aktiviteter der ikke er normale tachograf-aktiviteter."""
    if activity.activity_type != "normal":
        return
    if activity.source != ActivitySource.tachograph:
        return
    if activity.status != ActivityStatus.approved:
        return

    weekday = activity.start_time.weekday()
    duration = _effective_duration_minutes(activity)
    start_hour = activity.start_time.hour + activity.start_time.minute / 60.0

    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=activity.employee_id,
        weekday=weekday,
    ).first()

    if baseline is None:
        baseline = EmployeeBaseline(
            employee_id=activity.employee_id,
            weekday=weekday,
            sample_count=0,
            duration_mean_minutes=0.0,
            duration_m2_minutes=0.0,
            start_hour_mean=0.0,
            start_hour_m2=0.0,
            salt_count=0,
        )
        db.add(baseline)

    n = baseline.sample_count + 1
    baseline.sample_count = n

    # Welford's online algoritme for varighed
    dur_mean = float(baseline.duration_mean_minutes)
    dur_m2 = float(baseline.duration_m2_minutes)
    delta = duration - dur_mean
    dur_mean += delta / n
    delta2 = duration - dur_mean
    dur_m2 += delta * delta2
    baseline.duration_mean_minutes = dur_mean
    baseline.duration_m2_minutes = dur_m2

    # Welford's online algoritme for starttid
    sh_mean = float(baseline.start_hour_mean)
    sh_m2 = float(baseline.start_hour_m2)
    delta = start_hour - sh_mean
    sh_mean += delta / n
    delta2 = start_hour - sh_mean
    sh_m2 += delta * delta2
    baseline.start_hour_mean = sh_mean
    baseline.start_hour_m2 = sh_m2

    if activity.salt_supplement:
        baseline.salt_count = (baseline.salt_count or 0) + 1

    baseline.last_updated = datetime.utcnow()
    db.commit()


def rebuild_baselines_for_employee(employee_id: int, db: Session) -> int:
    """Slet og genberegn alle baselines for én medarbejder fra godkendte normale aktiviteter.
    Returnerer antal behandlede aktiviteter."""
    db.query(EmployeeBaseline).filter_by(employee_id=employee_id).delete()
    db.commit()

    activities = (
        db.query(Activity)
        .filter(
            Activity.employee_id == employee_id,
            Activity.activity_type == "normal",
            Activity.source == ActivitySource.tachograph,
            Activity.status == ActivityStatus.approved,
        )
        .order_by(Activity.start_time)
        .all()
    )

    for act in activities:
        update_baseline_from_activity(act, db)

    return len(activities)


def _effective_duration_minutes(activity: Activity) -> float:
    """Netto varighed i minutter efter pausefradrag."""
    total = (activity.end_time - activity.start_time).total_seconds() / 60.0
    for p in (activity.pause_intervals or []):
        try:
            ps = datetime.fromisoformat(p[0])
            pe = datetime.fromisoformat(p[1])
            actual_start = max(activity.start_time, ps)
            actual_end = min(activity.end_time, pe)
            if actual_end > actual_start:
                total -= (actual_end - actual_start).total_seconds() / 60.0
        except (ValueError, IndexError):
            pass
    return max(0.0, total)
