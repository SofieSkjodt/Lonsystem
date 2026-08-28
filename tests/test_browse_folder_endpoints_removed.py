"""
De server-side mappevælger-endpoints åbnede en native tkinter-dialog PÅ
SERVEREN, ikke hos brugeren. Da appen kører som en Windows-tjeneste uden
interaktivt skrivebord (Session 0-isolation), kan dialogen aldrig vises
eller lukkes af nogen – kaldet hænger for evigt og optager en tråd fra
uvicorns trådpulje permanent. Erstattet af almindelige tekstfelter til sti
i frontenden (se app.js). Disse tests låser fast, at routerne er fjernet.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from routers import import_ddd, payroll_router, payroll_settlement_router


def _route_paths(router):
    return {route.path for route in router.routes}


def test_ddd_browse_endpoints_removed():
    paths = _route_paths(import_ddd.router)
    assert "/api/browse-ddd-folder" not in paths
    assert "/api/browse-ddd-files" not in paths


def test_payroll_browse_folder_endpoint_removed():
    paths = _route_paths(payroll_router.router)
    assert "/api/payroll/browse-folder" not in paths
    # downloads-folder er ikke en tkinter-dialog – bruges stadig til at
    # forududfylde tekstfeltet, og skal blive stående.
    assert "/api/payroll/downloads-folder" in paths


def test_payroll_settlement_browse_folder_endpoint_removed():
    paths = _route_paths(payroll_settlement_router.router)
    assert "/api/payroll-settlement/browse-folder" not in paths
    assert "/api/payroll-settlement/downloads-folder" in paths
