"""
backup.py kørte hidtil uden nogen try/except omkring run_backup() ved
opstart via Windows Task Scheduler. En uventet fejl (disk fuld,
rettighedsfejl, fil låst af en anden proces) crashede scriptet med en
uhåndteret exception - ingen fejl-linje i backup.log, kun tavshed. Da
scheduled tasks ikke har nogen konsol, forsvandt selv Pythons egen
traceback-udskrift usynligt. main() skal fange det, logge fuld traceback,
og afslutte med en fejlkode.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backup'))

import logging

import pytest

_root_logger = logging.getLogger()
_handlers_before_import = list(_root_logger.handlers)

import backup as backup_module

# backup.py's logging.basicConfig() (kørt ved import) tilføjer en FileHandler
# der peger på den RIGTIGE backup/backup.log. Fjern den igen med det samme,
# så resten af testsuiten ikke uforvarende skriver testdata til den fil.
for _h in list(_root_logger.handlers):
    if _h not in _handlers_before_import:
        _root_logger.removeHandler(_h)


def test_main_runs_backup_successfully_without_raising(monkeypatch):
    monkeypatch.setattr(backup_module, "run_backup", lambda: None)
    backup_module.main()  # skal ikke rejse noget


def test_main_logs_full_error_and_exits_nonzero_on_backup_failure(monkeypatch, caplog):
    def _boom():
        raise RuntimeError("disk fuld")

    monkeypatch.setattr(backup_module, "run_backup", _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as exc_info:
            backup_module.main()

    assert exc_info.value.code == 1
    assert "disk fuld" in caplog.text
