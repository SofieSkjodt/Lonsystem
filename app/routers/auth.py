import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime
from time import time

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user, get_user_permissions, log_action, verify_password
from database.models import AppUser
from database.session import get_db

_ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "")
_ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "")

_jwks_cache: dict | None = None
_jwks_cache_at: float = 0.0
_JWKS_TTL = 3600.0


def _get_jwks(tenant_id: str) -> dict:
    global _jwks_cache, _jwks_cache_at
    now = time()
    if _jwks_cache and now - _jwks_cache_at < _JWKS_TTL:
        return _jwks_cache
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
        _jwks_cache = json.loads(resp.read())
        _jwks_cache_at = now
        return _jwks_cache

router = APIRouter(prefix="/api/auth", tags=["auth"])

_login_timestamps: dict[str, list[float]] = defaultdict(list)
_LOGIN_MAX = 5
_LOGIN_WINDOW = 60


def _check_login_rate(ip: str) -> None:
    now = time()
    recent = [t for t in _login_timestamps[ip] if now - t < _LOGIN_WINDOW]
    _login_timestamps[ip] = recent
    if len(recent) >= _LOGIN_MAX:
        raise HTTPException(429, f"For mange loginforsøg. Vent {_LOGIN_WINDOW} sekunder og prøv igen.")
    _login_timestamps[ip].append(now)


class LoginRequest(BaseModel):
    initials: str
    password: str


@router.post("/login")
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    _check_login_rate(request.client.host if request.client else "unknown")
    user = (
        db.query(AppUser)
        .filter(AppUser.initials.ilike(body.initials), AppUser.active == True)
        .first()
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Forkerte initialer eller adgangskode")
    ip = request.client.host if request.client else "unknown"
    _login_timestamps.pop(ip, None)
    request.session["user_id"] = user.id
    user.last_login = datetime.utcnow()
    log_action(db, user, "login", details=f"Login af {user.name} ({user.role})")
    db.commit()
    perms = get_user_permissions(db, user.role)
    return {
        "id": user.id,
        "name": user.name,
        "initials": user.initials,
        "role": user.role,
        "email": user.email or "",
        "permissions": perms,
    }


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


class SSORequest(BaseModel):
    id_token: str


@router.post("/sso")
async def sso_login(request: Request, body: SSORequest, db: Session = Depends(get_db)):
    if not _ENTRA_TENANT_ID or not _ENTRA_CLIENT_ID:
        raise HTTPException(400, "SSO er ikke konfigureret (ENTRA_TENANT_ID/CLIENT_ID mangler i .env)")
    try:
        jwks = _get_jwks(_ENTRA_TENANT_ID)
        header = jwt.get_unverified_header(body.id_token)
        kid = header.get("kid")
        key_data = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if not key_data:
            raise HTTPException(401, "Ukendt token-signeringsnøgle")
        public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))
        payload = jwt.decode(
            body.id_token,
            public_key,
            algorithms=["RS256"],
            audience=_ENTRA_CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{_ENTRA_TENANT_ID}/v2.0",
        )
        upn = payload.get("preferred_username") or payload.get("upn") or payload.get("email") or ""
        if not upn:
            raise HTTPException(401, "Ingen UPN i Entra-token")
        user = (
            db.query(AppUser)
            .filter(AppUser.email.ilike(upn), AppUser.active == True)
            .first()
        )
        if not user:
            raise HTTPException(401, f"Ingen aktiv bruger med Entra-konto: {upn}")
        request.session["user_id"] = user.id
        user.last_login = datetime.utcnow()
        log_action(db, user, "sso_login", details=f"Entra SSO-login af {user.name} ({user.role})")
        db.commit()
        perms = get_user_permissions(db, user.role)
        return {
            "id": user.id,
            "name": user.name,
            "initials": user.initials,
            "role": user.role,
            "email": user.email or "",
            "permissions": perms,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "SSO-verificering fejlede")


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db),
             current_user: AppUser = Depends(get_current_user)):
    perms = get_user_permissions(db, current_user.role)
    return {
        "id": current_user.id,
        "name": current_user.name,
        "initials": current_user.initials,
        "role": current_user.role,
        "email": current_user.email or "",
        "permissions": perms,
    }
