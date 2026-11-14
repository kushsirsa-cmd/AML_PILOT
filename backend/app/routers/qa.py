from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..auth import CAN
from ..deps import current_user, current_role
from ..models import AuditLog, QaReview
from ..modules import qa

router = APIRouter(prefix="/api/qa", tags=["qa"])


class SampleIn(BaseModel):
    days: int = Field(30, ge=1, le=365)
    low_risk_rate: float = Field(0.25, ge=0, le=1)


class CompleteIn(BaseModel):
    checklist: dict[str, str]
    findings: str | None = None


@router.get("/checklist")
def checklist():
    return dict(criteria=qa.CHECKLISTS["default"], critical=sorted(qa.CRITICAL_CRITERIA))


@router.post("/sample")
def sample(body: SampleIn = SampleIn(), db: Session = Depends(get_db), user: str = Depends(current_user)):
    created = qa.sample(db, days=body.days, low_risk_rate=body.low_risk_rate, actor=user)
    audit.log(db, actor=user, actor_type=audit.USER, action="QA_SAMPLE_DRAWN", entity_type="qa", details=dict(new_items=len(created), days=body.days))
    db.commit()
    return dict(created=len(created), items=[qa.qa_dict(q) for q in created])


@router.get("/reviews")
def reviews(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(QaReview).order_by(QaReview.id.desc())
    if status:
        stmt = stmt.where(QaReview.status == status)
    return [qa.qa_dict(q) for q in db.scalars(stmt)]


@router.get("/reviews/{qa_id}")
def review(qa_id: int, db: Session = Depends(get_db)):
    q = db.get(QaReview, qa_id)
    if not q:
        raise HTTPException(404, "QA review not found")
    row = db.get(AuditLog, q.audit_id)
    d = qa.qa_dict(q)
    d["decision"] = dict(action=row.action, actor=row.actor, entity_type=row.entity_type, entity_id=row.entity_id, ts=row.ts.isoformat(), details=row.details) if row else None
    return d


@router.post("/reviews/{qa_id}/complete")
def complete(qa_id: int, body: CompleteIn, db: Session = Depends(get_db), user: str = Depends(current_user), role: str = Depends(current_role)):
    if role not in CAN["qa_review"]:
        raise HTTPException(403, "QA reviews are completed by a Senior Analyst or Compliance Manager.")
    q = db.get(QaReview, qa_id)
    if not q:
        raise HTTPException(404, "QA review not found")
    if q.status == "COMPLETED":
        raise HTTPException(409, "Already completed")
    try:
        qa.complete(q, user, body.checklist, body.findings)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.log(db, actor=user, actor_type=audit.USER, action="QA_REVIEW_COMPLETED", entity_type="qa", entity_id=q.id, customer_id=q.customer_id,
              details=dict(outcome=q.outcome, score=q.score, decision_maker=q.decision_maker))
    db.commit()
    return qa.qa_dict(q)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    return qa.dashboard(db)
