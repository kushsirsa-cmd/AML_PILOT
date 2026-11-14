from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuditLog, Customer, Review, ScreeningHit
from ..schemas import CHANNELS, PRODUCTS
from ..serializers import customer_dict

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/meta")
def meta():
    return {"llm_active": settings.llm_active, "model": settings.claude_model if settings.llm_active else None,
            "products": PRODUCTS, "channels": CHANNELS}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count(Customer.id))) or 0
    dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "PROHIBITED": 0, "UNRATED": 0}
    for rating, n in db.execute(select(Customer.risk_rating, func.count(Customer.id)).group_by(Customer.risk_rating)).all():
        dist[rating or "UNRATED"] = n

    high = db.scalars(
        select(Customer).where(Customer.risk_rating.in_(["HIGH", "PROHIBITED"])).order_by(Customer.risk_score.desc())
    ).all()
    pending = db.execute(
        select(Review, Customer).join(Customer, Customer.id == Review.customer_id).where(Review.status == "PENDING").order_by(Review.id.desc())
    ).all()
    overdue = db.scalars(
        select(Customer).where(Customer.next_review_due < date.today(), Customer.status.in_(["ACTIVE", "UNDER_REVIEW"]))
    ).all()

    open_hits = db.execute(
        select(ScreeningHit, Customer).join(Customer, Customer.id == ScreeningHit.customer_id)
        .where(ScreeningHit.disposition == "OPEN", ScreeningHit.confidence >= 75).order_by(ScreeningHit.confidence.desc())
    ).all()
    by_list = {"SANCTIONS": 0, "PEP": 0, "ADVERSE_MEDIA": 0}
    for h, _ in open_hits:
        by_list[h.list_type] += 1

    recent = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(8)).all()
    return {
        "total_customers": total,
        "risk_distribution": dist,
        "high_risk_customers": [customer_dict(c) for c in high],
        "reviews_pending": {
            "count": len(pending),
            "periodic": sum(1 for r, _ in pending if r.review_type == "PERIODIC"),
            "event_driven": sum(1 for r, _ in pending if r.review_type == "EVENT_DRIVEN"),
            "items": [
                {"id": r.id, "review_type": r.review_type, "trigger": r.trigger, "recommendation": r.recommendation,
                 "customer_id": c.id, "customer_name": c.full_name, "customer_ref": c.customer_ref,
                 "priority": (r.outcome or {}).get("priority"), "created_at": r.created_at.isoformat()}
                for r, c in pending[:10]
            ],
        },
        "reviews_overdue": len(overdue),
        "screening_matches": {
            "open_total": len(open_hits),
            "by_list": by_list,
            "items": [
                {"id": h.id, "list_type": h.list_type, "matched_name": h.matched_name, "confidence": h.confidence,
                 "customer_id": c.id, "customer_name": c.full_name, "customer_ref": c.customer_ref}
                for h, c in open_hits[:10]
            ],
        },
        "recent_audit": [
            {"id": a.id, "ts": a.ts.isoformat(), "actor": a.actor, "actor_type": a.actor_type, "action": a.action,
             "customer_id": a.customer_id} for a in recent
        ],
    }
