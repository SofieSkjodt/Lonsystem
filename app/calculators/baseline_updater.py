from datetime import datetime

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline


_SAME_THRESHOLD_MINUTES = 0.5   # < 30 sekunder forskel = uændret
_SAME_THRESHOLD_HOURS  = 1 / 60  # < 1 minut forskel i starttid = uændret


def update_baseline_from_activity(activity: Activity, db: Session) -> None:
    """Opdaterer EmployeeBaseline for aktivitetens medarbejder+ugedag via Welford's algoritme.

    Regler:
    - Ikke-normale eller ikke-tachograf-aktiviteter ignoreres.
    - Hvis aktiviteten allerede har bidraget med identiske værdier (varighed +
      starttid), springes opdateringen over (re-approve uden ændringer tæller ikke dobbelt).
    - Hvis aktiviteten har bidraget tidligere men med andre værdier (tidspunkt ændret),
      fjernes det gamle bidrag fra baselinen (Welford downdate) inden det nye tilføjes.
    """
    if activity.activity_type != "normal":
        return
    if activity.source != ActivitySource.tachograph:
        return
    if activity.status != ActivityStatus.approved:
        return

    weekday = activity.start_time.weekday()
    duration = _effective_duration_minutes(activity)
    start_hour = activity.start_time.hour + activity.start_time.minute / 60.0

    prev_dur = activity.baseline_duration_minutes
    prev_sh  = activity.baseline_start_hour
    has_prev = prev_dur is not None and prev_sh is not None

    if has_prev:
        prev_dur = float(prev_dur)
        prev_sh  = float(prev_sh)
        if (
            abs(prev_dur - duration) < _SAME_THRESHOLD_MINUTES
            and abs(prev_sh - start_hour) < _SAME_THRESHOLD_HOURS
        ):
            return  # Uændret – tæller ikke dobbelt

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
        db.flush()

    # Fjern gammelt bidrag fra baselinen (Welford downdate)
    if has_prev and baseline.sample_count > 0:
        _welford_downdate(baseline, prev_dur, prev_sh)

    # Tilføj nyt bidrag (Welford update)
    n = baseline.sample_count + 1
    baseline.sample_count = n

    dur_mean = float(baseline.duration_mean_minutes)
    dur_m2   = float(baseline.duration_m2_minutes)
    delta    = duration - dur_mean
    dur_mean += delta / n
    dur_m2   += delta * (duration - dur_mean)
    baseline.duration_mean_minutes = dur_mean
    baseline.duration_m2_minutes   = max(0.0, dur_m2)

    sh_mean = float(baseline.start_hour_mean)
    sh_m2   = float(baseline.start_hour_m2)
    delta   = start_hour - sh_mean
    sh_mean += delta / n
    sh_m2   += delta * (start_hour - sh_mean)
    baseline.start_hour_mean = sh_mean
    baseline.start_hour_m2   = max(0.0, sh_m2)

    if activity.salt_supplement:
        baseline.salt_count = (baseline.salt_count or 0) + 1

    baseline.last_updated = datetime.utcnow()

    # Gem de bidragede værdier på aktiviteten
    activity.baseline_duration_minutes = duration
    activity.baseline_start_hour       = start_hour

    db.commit()


def rebuild_baselines_for_employee(employee_id: int, db: Session) -> int:
    """Slet og genberegn alle baselines for én medarbejder fra godkendte normale aktiviteter.
    Nulstiller også baseline-markørerne på aktiviteterne. Returnerer antal behandlede aktiviteter."""
    db.query(EmployeeBaseline).filter_by(employee_id=employee_id).delete()

    # Nulstil markører så downdate-logikken ikke forstyrrer genopbygningen
    db.query(Activity).filter(Activity.employee_id == employee_id).update(
        {
            "baseline_duration_minutes": None,
            "baseline_start_hour": None,
        },
        synchronize_session="fetch",
    )
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


def _welford_downdate(
    baseline: EmployeeBaseline,
    old_duration: float,
    old_start_hour: float,
) -> None:
    """Fjerner ét sample fra Welford's løbende statistik (in-place).

    Formel: given n samples med (mean, M2), fjern sample x:
        n'    = n - 1
        mean' = (n * mean - x) / n'
        M2'   = M2 - (x - mean) * (x - mean')
    """
    n = baseline.sample_count
    if n <= 0:
        return

    if n == 1:
        baseline.sample_count          = 0
        baseline.duration_mean_minutes = 0.0
        baseline.duration_m2_minutes   = 0.0
        baseline.start_hour_mean       = 0.0
        baseline.start_hour_m2         = 0.0
        return

    n_new = n - 1

    old_dur_mean = float(baseline.duration_mean_minutes)
    new_dur_mean = (n * old_dur_mean - old_duration) / n_new
    baseline.duration_mean_minutes = new_dur_mean
    baseline.duration_m2_minutes   = max(
        0.0,
        float(baseline.duration_m2_minutes)
        - (old_duration - old_dur_mean) * (old_duration - new_dur_mean),
    )

    old_sh_mean = float(baseline.start_hour_mean)
    new_sh_mean = (n * old_sh_mean - old_start_hour) / n_new
    baseline.start_hour_mean = new_sh_mean
    baseline.start_hour_m2   = max(
        0.0,
        float(baseline.start_hour_m2)
        - (old_start_hour - old_sh_mean) * (old_start_hour - new_sh_mean),
    )

    baseline.sample_count = n_new


def _effective_duration_minutes(activity: Activity) -> float:
    """Netto varighed i minutter efter pausefradrag."""
    total = (activity.end_time - activity.start_time).total_seconds() / 60.0
    # Kombinér manuelle pauser og 'rest'-segmenter fra tachograf
    pauses = list(activity.pause_intervals or [])
    for seg in (activity.segments or []):
        try:
            if len(seg) >= 3 and seg[2] == "rest":
                pauses.append([seg[0], seg[1]])
        except (TypeError, IndexError):
            pass
    for p in pauses:
        try:
            ps = datetime.fromisoformat(p[0])
            pe = datetime.fromisoformat(p[1])
            actual_start = max(activity.start_time, ps)
            actual_end   = min(activity.end_time, pe)
            if actual_end > actual_start:
                total -= (actual_end - actual_start).total_seconds() / 60.0
        except (ValueError, IndexError):
            pass
    return max(0.0, total)
