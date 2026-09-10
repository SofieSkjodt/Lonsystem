import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def test_employee_ot_extra_alle_timer_defaults_to_false(db, employee):
    assert employee.ot_extra_alle_timer is False
