from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..agents import pipeline
from ..db import get_db
from ..deps import current_user
from ..models import Customer, ScreeningHit
from ..schemas import AdhocScreenIn, DispositionIn
from ..screening_service import screen
from ..serializers import hit_dict
from .customers import detail

router = APIRouter(prefix="/api/screening", tags=["screening"])


@router.get("/hits")
def list_hits(disposition: str | None = None, list_type: str | None = None, min_confidence: float = 0, db: Session = Depends(get_db)):
    stmt = (
        select(ScreeningHit, Customer)
        .join(Customer, Customer.id == ScreeningHit.customer_id)
        .where(ScreeningHit.confidence >= min_confidence)
        .order_by(ScreeningHit.confidence.desc())
    )
    if disposition:
        stmt = stmt.where(ScreeningHit.disposition == disposition)
    if list_type:
        stmt = stmt.where(ScreeningHit.list_type == list_type)
    return [
        {**hit_dict(h), "customer": {"id": c.id, "customer_ref": c.customer_ref, "full_name": c.full_name, "risk_rating": c.risk_rating}}
        for h, c in db.execute(stmt).all()
    ]


@router.post("/hits/{hit_id}/disposition")
def disposition(hit_id: int, body: DispositionIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    h = db.get(ScreeningHit, hit_id)
    if not h:
        raise HTTPException(404, "Hit not found")
    if body.disposition != "OPEN" and not (body.note and len(body.note.strip()) >= 3):
        raise HTTPException(422, "A rationale note is required when dispositioning a hit.")
    old = h.disposition
    h.disposition, h.disposition_note = body.disposition, body.note
    c = db.get(Customer, h.customer_id)
    audit.log(db, actor=user, actor_type=audit.USER, action="SCREENING_HIT_DISPOSITION", entity_type="screening_hit",
              entity_id=h.id, customer_id=c.id,
              details={"list_type": h.list_type, "matched_name": h.matched_name, "from": old, "to": body.disposition, "note": body.note})
    db.flush()
    # re-evaluate everything downstream of screening so the rating reflects the analyst's decision
    ctx = pipeline.load_context(db, c, user, trigger="HIT_DISPOSITION")
    for name in ("screening", "edd", "risk", "summary"):
        pipeline.run_agent(db, c, name, ctx, actor=user)
    db.commit()
    return detail(db, c)


@router.post("/adhoc")
def adhoc(body: AdhocScreenIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Stateless name screening (no customer attached) - handy for testing the matcher."""
    res = screen(body.name, body.date_of_birth, body.nationality)
    audit.log(db, actor=user, actor_type=audit.USER, action="ADHOC_SCREENING", entity_type="screening", customer_id=None,
              details={"name": body.name, "matches": {k: len(v) for k, v in res.items()}})
    db.commit()
    return res
