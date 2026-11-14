from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog

USER, AI, SYSTEM = "USER", "AI", "SYSTEM"


def log(
    db: Session,
    *,
    actor: str,
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    customer_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Append an audit row to the current transaction (caller commits)."""
    row = AuditLog(
        actor=actor,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        customer_id=customer_id,
        details=details or {},
    )
    db.add(row)
    return row
