from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..models import Alert

OPEN_STATUSES = ("OPEN", "IN_REVIEW", "ESCALATED_MLRO", "SAR_DRAFTED")


def raise_alert(
    db: Session, *, source: str, entity_type: str, entity_id: int, title: str, description: str, severity: str,
    customer_id: int | None = None, details: dict | None = None,
) -> Alert:
    """Create an alert, or refresh the existing open one (de-duplicated by source/entity/title)."""
    existing = db.scalar(
        select(Alert).where(
            Alert.source == source, Alert.entity_type == entity_type, Alert.entity_id == entity_id,
            Alert.title == title, Alert.status.in_(OPEN_STATUSES),
        )
    )
    if existing:
        existing.description, existing.severity, existing.details = description, severity, details or {}
        return existing
    a = Alert(source=source, entity_type=entity_type, entity_id=entity_id, customer_id=customer_id, severity=severity,
              title=title, description=description, details=details or {})
    db.add(a)
    db.flush()
    audit.log(db, actor=f"{source.title()} monitoring", actor_type=audit.SYSTEM, action="ALERT_RAISED", entity_type="alert",
              entity_id=a.id, customer_id=customer_id, details={"source": source, "severity": severity, "title": title})
    return a


# ---------------------------------------------------------------------------------------------
# Screening alerts: one alert per open sanctions / PEP / adverse-media hit; closed automatically when the hit is discounted.
# ---------------------------------------------------------------------------------------------
SCREENING_SOURCES = {"SANCTIONS": "Sanctions match", "PEP": "PEP match", "ADVERSE_MEDIA": "Adverse media"}


def sync_screening_alerts(db: Session, customer_id: int) -> None:
    from datetime import datetime, timezone

    from ..models import ScreeningHit

    hits = list(db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == customer_id)))
    existing = {
        (a.details or {}).get("hit_id"): a
        for a in db.scalars(select(Alert).where(Alert.entity_type == "customer", Alert.entity_id == customer_id, Alert.source.in_(list(SCREENING_SOURCES))))
    }
    for h in hits:
        a = existing.get(h.id)
        if h.disposition == "OPEN" and h.confidence >= 75:
            if a is None:
                rec = (h.details or {}).get("record", {})
                sev = "CRITICAL" if (h.list_type == "SANCTIONS" and h.confidence >= 90) else "HIGH" if h.list_type != "ADVERSE_MEDIA" or rec.get("severity") == "HIGH" else "MEDIUM"
                desc = {"SANCTIONS": f"{rec.get('list', 'Sanctions list')} / {rec.get('program', '')}: {rec.get('reason', '')}",
                        "PEP": f"{rec.get('position', 'Politically exposed person')} ({rec.get('category', '')})",
                        "ADVERSE_MEDIA": rec.get("headline", "Adverse media")}[h.list_type]
                a = Alert(source=h.list_type, entity_type="customer", entity_id=customer_id, customer_id=customer_id, severity=sev,
                          title=f"{SCREENING_SOURCES[h.list_type]}: {h.matched_name} ({h.confidence:.0f}%)", description=desc,
                          details={"hit_id": h.id, "list_type": h.list_type, "confidence": h.confidence})
                db.add(a)
                db.flush()
                audit.log(db, actor="Screening monitoring", actor_type=audit.SYSTEM, action="ALERT_RAISED", entity_type="alert", entity_id=a.id,
                          customer_id=customer_id, details={"source": h.list_type, "severity": sev, "title": a.title})
        elif a is not None and h.disposition == "FALSE_POSITIVE" and a.status != "CLOSED":
            a.status, a.closed_at = "CLOSED", datetime.now(timezone.utc)
            a.resolution = f"Hit dispositioned as false positive: {h.disposition_note or ''}".strip()
