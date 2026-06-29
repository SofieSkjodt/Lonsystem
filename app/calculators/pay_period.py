"""
Lønperioder: faste 14-dages perioder, mandag til søndag.
Anker: mandag 1/6-2026 (bekræftet af eksempel i kravdokumentet:
dags dato 3/6-2026 -> lønperiode 1/6-14/6).
Perioderne flugter dermed med lige/ulige uger i timefordelingen.
"""

from datetime import date, timedelta
from sqlalchemy.orm import Session
from database.models import PayPeriod, PayPeriodStatus

# Anker-mandag for periodeberegning
PERIOD_ANCHOR = date(2026, 6, 1)  # mandag, ISO-uge 23


def period_start_for_date(d: date) -> date:
    """Beregn startdatoen (mandag) for den 14-dages periode der indeholder d."""
    delta_days = (d - PERIOD_ANCHOR).days
    period_index = delta_days // 14
    return PERIOD_ANCHOR + timedelta(days=period_index * 14)


def is_even_week(d: date) -> bool:
    """Lige uge = ISO-ugenummeret er lige."""
    return d.isocalendar()[1] % 2 == 0


def period_for_date(d: date, db: Session) -> PayPeriod | None:
    return (
        db.query(PayPeriod)
        .filter(PayPeriod.start_date <= d, PayPeriod.end_date >= d)
        .first()
    )


def get_or_create_period_for_date(d: date, db: Session) -> PayPeriod:
    """Returnér perioden der indeholder d – opret hvis den ikke findes.

    Håndterer race condition: to samtidige requests kan begge finde at perioden
    mangler og forsøge at oprette den. Den anden INSERT fejler med IntegrityError
    (start_date er UNIQUE). I det tilfælde rulles transaktionen tilbage og
    perioden læses i stedet – den er nu oprettet af den første request.
    """
    period = period_for_date(d, db)
    if period:
        return period

    start = period_start_for_date(d)
    end = start + timedelta(days=13)

    try:
        period = PayPeriod(start_date=start, end_date=end, status=PayPeriodStatus.open)
        db.add(period)
        db.commit()
        db.refresh(period)
        return period
    except Exception:
        db.rollback()
        return period_for_date(d, db)
