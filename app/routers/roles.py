from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import ALL_PERMISSIONS, log_action, require_permission
from database.models import AppUser, Role
from database.session import get_db

router = APIRouter(prefix="/api/roles", tags=["roles"])

_access = require_permission("user_management")


class RoleCreate(BaseModel):
    name: str
    display_name: str
    permissions: List[str] = []


class RoleUpdate(BaseModel):
    display_name: Optional[str] = None
    permissions: Optional[List[str]] = None


def _to_response(r: Role) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "display_name": r.display_name,
        "is_system": r.is_system,
        "permissions": r.permissions or [],
    }


@router.get("")
def list_roles(current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    return [_to_response(r) for r in db.query(Role).order_by(Role.name).all()]


@router.post("", status_code=201)
def create_role(body: RoleCreate, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    if db.query(Role).filter(Role.name == body.name).first():
        raise HTTPException(400, "Rollenavn er allerede i brug")
    invalid = set(body.permissions) - set(ALL_PERMISSIONS.keys())
    if invalid:
        raise HTTPException(400, f"Ukendte rettigheder: {', '.join(sorted(invalid))}")
    role = Role(name=body.name, display_name=body.display_name,
                permissions=body.permissions, is_system=False)
    db.add(role)
    db.flush()
    log_action(db, current_user, "create_role", "role", role.id, f"Oprettet rolle {role.name}")
    db.commit()
    db.refresh(role)
    return _to_response(role)


@router.patch("/{role_id}")
def update_role(role_id: int, body: RoleUpdate, current_user: AppUser = Depends(_access),
                db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(404, "Rolle ikke fundet")
    if body.display_name is not None:
        role.display_name = body.display_name
    if body.permissions is not None:
        if role.is_system:
            raise HTTPException(400, "Systemrollers rettigheder kan ikke ændres")
        invalid = set(body.permissions) - set(ALL_PERMISSIONS.keys())
        if invalid:
            raise HTTPException(400, f"Ukendte rettigheder: {', '.join(sorted(invalid))}")
        role.permissions = body.permissions
    log_action(db, current_user, "update_role", "role", role.id, f"Opdateret rolle {role.name}")
    db.commit()
    db.refresh(role)
    return _to_response(role)


@router.delete("/{role_id}", status_code=204)
def delete_role(role_id: int, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(404, "Rolle ikke fundet")
    if role.is_system:
        raise HTTPException(400, "Systemroller kan ikke slettes")
    if db.query(AppUser).filter(AppUser.role == role.name).count() > 0:
        raise HTTPException(400, "Rollen er i brug – flyt brugerne til en anden rolle først")
    log_action(db, current_user, "delete_role", "role", role.id, f"Slettet rolle {role.name}")
    db.delete(role)
    db.commit()
