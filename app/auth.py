import bcrypt

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database.models import AppUser
from database.session import get_db

ALL_PERMISSIONS = {
    "payroll":             "Lønkørsel",
    "absence_overview":    "Fraværsoversigt",
    "import_ddd":          "Importer .ddd",
    "user_management":     "Brugerstyring",
    "reopen_period":       "Åbn låst lønperiode",
    "stamdata":            "Stamdata",
    "view_employees":      "Se medarbejdere",
    "manage_employees":    "Tilføj medarbejdere",
    "view_vehicles":       "Se vognpark",
    "manage_vehicles":     "Tilføj vogn",
    "manage_employee_supplements": "Administrér medarbejdertillæg",
    "manage_holidays":     "Administrér helligdage",
    "anciennitet_alert":   "Anciennitetsvarsel",
    "approve_activities":  "Godkend aktiviteter",
    "view_calendar":       "Se aktivitetskalender",
    "toggle_springer":     "Sæt springertillæg",
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AppUser:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Ikke logget ind")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Ugyldig session")
    return user


def _role_has_permission(db: Session, role_name: str, perm: str) -> bool:
    from database.models import Role
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return False
    if role.is_system:
        return True
    return perm in (role.permissions or [])


def user_has_permission(db: Session, user: AppUser, perm: str) -> bool:
    return _role_has_permission(db, user.role, perm)


def require_permission(perm: str):
    def checker(request: Request, db: Session = Depends(get_db)) -> AppUser:
        user_id = request.session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Ikke logget ind")
        user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.active == True).first()
        if not user:
            raise HTTPException(status_code=401, detail="Ugyldig session")
        if not _role_has_permission(db, user.role, perm):
            raise HTTPException(status_code=403, detail="Ingen adgang")
        return user
    return checker


def get_user_permissions(db: Session, role_name: str) -> list:
    from database.models import Role
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return []
    if role.is_system:
        return list(ALL_PERMISSIONS.keys())
    return role.permissions or []


def log_action(db: Session, user: AppUser, action: str,
               entity_type: str = None, entity_id: int = None, details: str = None):
    from database.models import AuditLog
    entry = AuditLog(
        user_id=user.id,
        user_initials=user.initials,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
