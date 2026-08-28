"""
_safe_save_dir() tillod hidtil at gemme CSV/PDF-eksport hvor som helst på
C:\\ eller D:\\ (den deklarerede _ALLOWED_SAVE_ROOTS-liste blev aldrig
faktisk brugt til at begrænse noget). Nu skal den kun tillade stier under
brugerens/tjeneste-kontoens hjemmemappe, jf. utils/safe_paths.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from pathlib import Path

import pytest
from fastapi import HTTPException

from routers.payroll_router import _safe_save_dir


def test_path_under_home_is_accepted():
    target = str(Path.home() / "Downloads" / "loenfiler")
    result = _safe_save_dir(target)
    assert result == Path(target).resolve()


def test_path_outside_home_is_rejected():
    outside = str(Path(Path.home().anchor) / "et-helt-andet-sted")
    with pytest.raises(HTTPException) as exc_info:
        _safe_save_dir(outside)
    assert exc_info.value.status_code == 400


def test_app_directory_is_still_rejected_even_if_under_home():
    from routers.payroll_router import BASE_DIR
    with pytest.raises(HTTPException) as exc_info:
        _safe_save_dir(str(BASE_DIR))
    assert exc_info.value.status_code == 400
