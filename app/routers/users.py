from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user, hash_password, log_action, require_permission
from database.models import AppUser
from database.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])

_access = require_permission("user_management")


class UserCreate(BaseModel):
    name: str
    initials: str
    email: Optional[str] = None
    role: str
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    initials: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    password: Optional[str] = None
    active: Optional[bool] = None


def _to_response(u: AppUser) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "initials": u.initials,
        "email": u.email or "",
        "role": u.role,
        "active": u.active,
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


@router.get("")
def list_users(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    users = db.query(AppUser).order_by(AppUser.name).all()
    return [_to_response(u) for u in users]


@router.post("", status_code=201)
def create_user(
    body: UserCreate,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if db.query(AppUser).filter(AppUser.initials.ilike(body.initials)).first():
        raise HTTPException(400, "Initialer er allerede i brug")
    user = AppUser(
        name=body.name,
        initials=body.initials.upper(),
        email=body.email,
        role=body.role,
        password_hash=hash_password(body.password),
        active=True,
    )
    db.add(user)
    db.flush()
    log_action(db, current_user, "create_user", "user", user.id, f"Oprettet bruger {user.initials}")
    db.commit()
    db.refresh(user)
    return _to_response(user)


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UserUpdate,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        raise HTTPException(404, "Bruger ikke fundet")
    if body.initials and body.initials.upper() != user.initials:
        if db.query(AppUser).filter(AppUser.initials.ilike(body.initials)).first():
            raise HTTPException(400, "Initialer er allerede i brug")
        user.initials = body.initials.upper()
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = body.email
    if body.role is not None and body.role != user.role:
        old_role = user.role
        user.role = body.role
        log_action(db, current_user, "role_change", "user", user.id,
                   f"Rolle ændret fra '{old_role}' til '{body.role}' for {user.initials}")
    if body.password:
        user.password_hash = hash_password(body.password)
    if body.active is not None:
        user.active = body.active
    log_action(db, current_user, "update_user", "user", user.id, f"Opdateret bruger {user.initials}")
    db.commit()
    db.refresh(user)
    return _to_response(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        raise HTTPException(404, "Bruger ikke fundet")
    if user.id == current_user.id:
        raise HTTPException(400, "Du kan ikke slette din egen konto")
    log_action(db, current_user, "delete_user", "user", user.id, f"Slettet bruger {user.initials}")
    db.delete(user)
    db.commit()


@router.get("/audit-log")
def get_audit_log(
    limit: int = 500,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    from database.models import AuditLog
    entries = (
        db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "user_initials": e.user_initials,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "details": e.details,
        }
        for e in entries
    ]
