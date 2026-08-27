from math import sqrt

from sqlalchemy.orm import Session

from database.models import Activity, ActivitySource, ActivityStatus, EmployeeBaseline
from calculators.baseline_updater import _effective_duration_minutes, is_auto_approval_enabled

MIN_SAMPLES = 5
DURATION_STD_MULTIPLIER = 2.5
DURATION_TOLERANCE_FALLBACK = 0.30
START_HOUR_TOLERANCE_HOURS = 1.5


def should_auto_approve(activity: Activity, db: Session) -> tuple[bool, list[str]]:
    """Vurder om en aktivitet kan auto-godkendes mod medarbejderens historiske baseline.

    Returnerer (True, []) hvis aktiviteten falder inden for normale grænser,
    eller (False, [årsag, ...]) med en eller flere flagbeskrivelser.
    """
    if activity.activity_type != "normal":
        return False, ["Kun normale tachograf-aktiviteter auto-godkendes"]
    if activity.source != ActivitySource.tachograph:
        return False, ["Kun tachograf-aktiviteter auto-godkendes"]
    if not is_auto_approval_enabled(db):
        return False, ["Automatisk godkendelse er slået fra i systemindstillinger"]

    weekday = activity.start_time.weekday()
    baseline = db.query(EmployeeBaseline).filter_by(
        employee_id=activity.employee_id,
        weekday=weekday,
    ).first()

    if baseline is None or baseline.sample_count < MIN_SAMPLES:
        count = baseline.sample_count if baseline else 0
        return False, [f"Ikke nok data ({count}/{MIN_SAMPLES} registreringer for denne ugedag)"]

    flags = []
    n = baseline.sample_count

    # --- Varighed ---
    duration = _effective_duration_minutes(activity)
    dur_mean = float(baseline.duration_mean_minutes)
    dur_std = sqrt(float(baseline.duration_m2_minutes) / n) if n > 1 else 0.0
    dur_tolerance = max(dur_std * DURATION_STD_MULTIPLIER, dur_mean * DURATION_TOLERANCE_FALLBACK)

    if abs(duration - dur_mean) > dur_tolerance:
        direction = "for lang" if duration > dur_mean else "for kort"
        flags.append(
            f"Varighed afviger: {duration:.0f}min vs. typisk {dur_mean:.0f}±{dur_std:.0f}min ({direction})"
        )

    # --- Starttid ---
    start_hour = activity.start_time.hour + activity.start_time.minute / 60.0
    sh_mean = float(baseline.start_hour_mean)
    sh_std = sqrt(float(baseline.start_hour_m2) / n) if n > 1 else 0.0
    sh_tolerance = max(sh_std * DURATION_STD_MULTIPLIER, START_HOUR_TOLERANCE_HOURS)

    if abs(start_hour - sh_mean) > sh_tolerance:
        mean_h = int(sh_mean)
        mean_m = int((sh_mean % 1) * 60)
        act_h = activity.start_time.hour
        act_m = activity.start_time.minute
        flags.append(
            f"Starttid afviger: {act_h:02d}:{act_m:02d} vs. typisk {mean_h:02d}:{mean_m:02d} (±{sh_std:.1f}t)"
        )

    return len(flags) == 0, flags
