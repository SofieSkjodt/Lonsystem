# Søn/Helligdage Lønberegning – SDD Progress Ledger

Plan: docs/superpowers/plans/2026-06-23-son-helligdage-loen.md
Started: 2026-06-23

## Tasks

- [x] Task 1: DayType-klassifikator og special-day overtime-beregner (review clean)
- [x] Task 2: SH-løntypekoder i stamdata (kode 4 og 63) (review clean, inline logging fix)
- [x] Task 3: Opdater _calculate_employee() med SH-beregning (verified 2026-06-23)
- [x] Task 4: Opdater CSV-eksporten med SH-rækker (verified 2026-06-23)

## Status: COMPLETE

## Ændrede filer
- app/calculators/overtime.py — sh_kode8_hours, sh_kode9_hours felter
- app/calculators/day_type.py — ny fil: DayType, classify_day, compute_sh_hours, calculate_special_day_overtime
- app/calculators/pay_rates.py — DANLOEN_CODE_SH_FULDLOENNET="4", DANLOEN_CODE_SH_TIMELOENNET="63"
- app/database/session.py — _ensure_sh_pay_types() + kald fra init_db()
- app/routers/payroll_router.py — SH-beregning i _calculate_employee(), SH-rækker i CSV (GET+POST)

## Kendte minor-findings (fra reviewers)
- session.py: _ensure_sh_pay_types commit-mønster afviger lidt fra øvrige seeders (acceptabelt)
- session.py: ingen info-log ved idempotent skip (acceptabelt)
- plan.md brugte 'ot.normal_hours' i day_kr — rettet til 'ot.total_hours' (bevarer korrekt base-løn for OT-timer på normale dage)
