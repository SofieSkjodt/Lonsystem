import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from database.models import EmployeeBaseline


def test_employee_baseline_model_exists():
    assert hasattr(EmployeeBaseline, 'employee_id')
    assert hasattr(EmployeeBaseline, 'sample_count')
    assert hasattr(EmployeeBaseline, 'duration_mean_minutes')
    assert hasattr(EmployeeBaseline, 'duration_m2_minutes')
    assert hasattr(EmployeeBaseline, 'start_hour_mean')
    assert hasattr(EmployeeBaseline, 'start_hour_m2')
    assert hasattr(EmployeeBaseline, 'salt_count')
