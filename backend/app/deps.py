from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import read_token
from .config import settings
from .db import get_db
from .models import Customer, User


def _identity(authorization: str | None, x_analyst: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        u = read_token(authorization[7:].strip())
        if not u:
            raise HTTPException(401, "Session expired or invalid - please sign in again.")
        return u
    if settings.demo_open_access:
        return (x_analyst or "analyst.demo").strip()[:100] or "analyst.demo"
    raise HTTPException(401, "Authentication required.")


def current_user(authorization: str | None = Header(default=None), x_analyst: str | None = Header(default=None)) -> str:
    """Identity from a signed Bearer token (login) or, in DEMO_OPEN_ACCESS mode, the X-Analyst header."""
    return _identity(authorization, x_analyst)


def current_role(user: str = Depends(current_user), db: Session = Depends(get_db)) -> str:
    """Role always comes from the users table, never from a client-supplied header."""
    u = db.scalar(select(User).where(User.username == user))
    if u is not None and not u.active:
        raise HTTPException(403, "This account is deactivated.")
    return u.role if u else "ANALYST"


def require_role(*allowed: str):
    def dep(role: str = Depends(current_role)) -> str:
        if role not in allowed:
            raise HTTPException(403, f"Your role ({role}) cannot do this. Required: {' / '.join(allowed)}.")
        return role

    return dep


def get_customer_or_404(customer_id: int, db: Session = Depends(get_db)) -> Customer:
    c = db.get(Customer, customer_id)
    if not c:
        raise HTTPException(404, "Customer not found")
    return c
