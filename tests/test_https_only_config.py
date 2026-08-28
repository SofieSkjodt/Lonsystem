"""
Appen kørte hidtil altid med https_only=False på session-cookien, uanset
miljø – fordi produktionen (indtil nu) heller ikke havde TLS foran uvicorn.
Nu hvor der lægges en TLS-terminerende reverse proxy (Caddy) foran, skal
cookien kun sendes over HTTPS i produktion – men den skal stadig kunne
sættes til False i lokal udvikling, hvor der typisk ikke køres med TLS.
Styres via miljøvariablen HTTPS_ONLY (se .env / .env.example).
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import importlib


def _session_middleware_kwargs():
    import main
    importlib.reload(main)
    mw = next(m for m in main.app.user_middleware if m.cls.__name__ == "SessionMiddleware")
    return mw.kwargs


def test_https_only_defaults_to_false_for_local_dev(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-import")
    monkeypatch.delenv("HTTPS_ONLY", raising=False)
    assert _session_middleware_kwargs()["https_only"] is False


def test_https_only_enabled_when_env_var_set(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-import")
    monkeypatch.setenv("HTTPS_ONLY", "true")
    assert _session_middleware_kwargs()["https_only"] is True
