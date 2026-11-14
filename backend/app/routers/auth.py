from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..auth import CAN, ROLE_LABEL, ROLES, make_token
from ..config import settings
from ..db import get_db
from ..deps import current_role, current_user, require_role
from ..models import User

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None


def udict(u: User) -> dict:
    return dict(id=u.id, username=u.username, full_name=u.full_name, role=u.role, role_label=ROLE_LABEL.get(u.role, u.role), email=u.email, active=u.active)


@router.get("/auth/users")
def demo_users(db: Session = Depends(get_db)):
    """Listed on the login page so stakeholders can pick a persona in one click (demo only)."""
    return dict(users=[udict(u) for u in db.scalars(select(User).where(User.active.is_(True)).order_by(User.id))], demo_password=settings.demo_password)


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == body.username.strip()))
    if not u or body.password != settings.demo_password:
        raise HTTPException(401, "Invalid username or password.")
    if not u.active:
        raise HTTPException(403, "This account is deactivated.")
    audit.log(db, actor=u.username, actor_type=audit.USER, action="LOGIN", entity_type="user", entity_id=u.id, details={"role": u.role})
    db.commit()
    return dict(token=make_token(u.username), user=udict(u))


@router.get("/auth/me")
def me(user: str = Depends(current_user), role: str = Depends(current_role), db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == user))
    return dict(user=udict(u) if u else dict(username=user, full_name=user, role=role, role_label=ROLE_LABEL.get(role, role), email="", active=True),
                permissions={k: role in v for k, v in CAN.items()})


@router.get("/admin/users")
def list_users(db: Session = Depends(get_db), _: str = Depends(require_role(*CAN["admin"]))):
    return [udict(u) for u in db.scalars(select(User).order_by(User.id))]


@router.patch("/admin/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), actor: str = Depends(current_user), _: str = Depends(require_role(*CAN["admin"]))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(422, f"Role must be one of {ROLES}")
        u.role = body.role
    if body.active is not None:
        if u.username == actor and not body.active:
            raise HTTPException(409, "You cannot deactivate your own account.")
        u.active = body.active
    audit.log(db, actor=actor, actor_type=audit.USER, action="USER_UPDATED", entity_type="user", entity_id=u.id, details=body.model_dump(exclude_none=True))
    db.commit()
    return udict(u)
