from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/audit")
def list_audit(
    customer_id: int | None = None,
    actor_type: str | None = Query(default=None, description="USER | AI | SYSTEM"),
    action: str | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog)
    if customer_id is not None:
        stmt = stmt.where(AuditLog.customer_id == customer_id)
    if actor_type:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            {"id": a.id, "ts": a.ts.isoformat(), "actor": a.actor, "actor_type": a.actor_type, "action": a.action,
             "entity_type": a.entity_type, "entity_id": a.entity_id, "customer_id": a.customer_id, "details": a.details}
            for a in rows
        ],
    }
