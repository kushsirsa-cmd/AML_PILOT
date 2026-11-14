from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..agents import event_driven, periodic
from ..agents.risk import next_review_date
from ..db import get_db
from ..deps import current_user, get_customer_or_404
from ..models import Customer, Review
from ..schemas import EventIn, ReviewDecisionIn
from ..serializers import customer_dict, review_dict
from .customers import detail

router = APIRouter(prefix="/api", tags=["reviews"])


@router.get("/reviews")
def list_reviews(status: str | None = None, review_type: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Review, Customer).join(Customer, Customer.id == Review.customer_id).order_by(Review.id.desc())
    if status:
        stmt = stmt.where(Review.status == status)
    if review_type:
        stmt = stmt.where(Review.review_type == review_type)
    return [
        {**review_dict(r), "customer": {"id": c.id, "customer_ref": c.customer_ref, "full_name": c.full_name, "risk_rating": c.risk_rating}}
        for r, c in db.execute(stmt).all()
    ]


@router.post("/customers/{customer_id}/reviews/periodic", status_code=201)
def run_periodic(c: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db), user: str = Depends(current_user)):
    audit.log(db, actor=user, actor_type=audit.USER, action="PERIODIC_REVIEW_REQUESTED", entity_type="customer",
              entity_id=c.id, customer_id=c.id, details={})
    periodic.run(db, c, actor=user)
    return detail(db, c)


@router.post("/customers/{customer_id}/reviews/event", status_code=201)
def run_event(body: EventIn, c: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db), user: str = Depends(current_user)):
    try:
        event_driven.run(db, c, body.event_type, body.payload, actor=user)
    except event_driven.EventError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return detail(db, c)


@router.post("/reviews/{review_id}/decision")
def decide_review(review_id: int, body: ReviewDecisionIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    if r.status != "PENDING":
        raise HTTPException(409, f"Review already {r.status}")
    c = db.get(Customer, r.customer_id)
    if body.decision.startswith("COMPLETE") and c.risk_rating == "PROHIBITED":
        raise HTTPException(409, "Cannot complete a review for a PROHIBITED customer; escalate or exit the relationship.")

    r.decision, r.decision_note, r.decided_by = body.decision, body.note, user
    if body.decision.startswith("COMPLETE"):
        r.status, r.completed_at = "COMPLETED", datetime.now(timezone.utc)
        c.last_kyc_review = date.today()
        c.next_review_due = next_review_date(c.risk_rating or "MEDIUM", c.last_kyc_review)
        if c.status == "UNDER_REVIEW":
            c.status = "ACTIVE"
    elif body.decision == "ESCALATE":
        r.status = "ESCALATED"
        c.status = "UNDER_REVIEW"
    else:  # EXIT_RELATIONSHIP
        r.status, r.completed_at = "COMPLETED", datetime.now(timezone.utc)
        c.status = "EXITING"
    audit.log(db, actor=user, actor_type=audit.USER, action="REVIEW_DECISION", entity_type="review", entity_id=r.id,
              customer_id=c.id, details={"decision": body.decision, "note": body.note, "review_type": r.review_type,
                                         "customer_status": c.status})
    db.commit()
    return {"review": review_dict(r), "customer": customer_dict(c)}
