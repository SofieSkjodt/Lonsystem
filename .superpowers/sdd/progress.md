# Medarbejdertillæg — SDD Progress Ledger

Plan: docs/superpowers/plans/2026-08-13-medarbejder-tillaeg.md
Started: 2026-08-13

## Tasks

- [x] Task 1: complete (commits cbe54fd..35e9f07, review clean)
- [x] Task 2: complete (commits 35e9f07..b74a804, review clean; Minor: log_action commit not atomic with row create, audit action string not snake_case, no 404 on unknown employee_id in GET endpoints — carried to final review)
- [x] Task 3: complete (commits b74a804..96666af, review clean; Minor: local-import rationale comment cites imprecise precedent, cosmetic only)
- [x] Task 4: complete (commits 96666af..8fd2090, review clean; 1 Important fix applied: stale state.employees cache hid inactive employees in Tillæg-view; Minor: pre-existing shared-state pattern can transiently leak inactive employees into Aktiviteter-filter, not a new regression)
- [x] Task 5: complete (commits 8fd2090..c1d4c54, review clean; both ⚠️ items resolved by controller: value is float end-to-end, confirmEmployee() payload confirmed excludes the field)

## Final whole-branch review

- Round 1 (commits c1d4c54..0c9c053): 4 Important + 9 Minor found. User decisions: add "Afslut tillæg" endpoint/button; align Fraværsoversigt sygdom/barsel/skole_kursus rate with payroll. All 10 points (A-J) fixed in one wave; mid-fix contradiction on end-date semantics escalated to user, resolved as "ends at current pay period boundary, not today/yesterday".
- Round 2 (commits 0c9c053..da91a1d): re-review found the new UniqueConstraint(employee_id,end_date) collided with the period-boundary end rule, and the constraint/index were missing from the already-existing lonsystem.db (create_all skips existing tables). Fixed: replaced with a partial unique index (open-row-only invariant) + idempotent _migrate() addition, verified non-destructively against the real db. Plus 3 minor UX/safety fixes.
- Round 3 (confirmation review, commit da91a1d): clean, no findings. **Ready to merge: Yes.**

## Status: ALL TASKS COMPLETE — final review clean, ready for finishing-a-development-branch
