import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..agents import pipeline
from ..db import get_db
from ..auth import CAN
from ..deps import current_role, current_user, get_customer_or_404
from ..models import Assessment, CaseNote, Customer, Document, Review, ScreeningHit
from ..schemas import CustomerIn, CustomerUpdate, DecisionIn, DocumentIn
from ..serializers import (
    assessment_dict, customer_dict, document_dict, hit_dict, note_dict, review_dict,
)

router = APIRouter(prefix="/api", tags=["customers"])

DECISION_STATUS = {"APPROVE": "ACTIVE", "REJECT": "REJECTED", "ESCALATE": "UNDER_REVIEW", "REQUEST_INFO": "ONBOARDING"}


def detail(db: Session, c: Customer) -> dict:
    latest: dict[str, dict] = {}
    for a in db.scalars(select(Assessment).where(Assessment.customer_id == c.id).order_by(Assessment.id)):
        latest[a.agent] = assessment_dict(a)
    hits = db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == c.id).order_by(ScreeningHit.confidence.desc()))
    reviews = db.scalars(select(Review).where(Review.customer_id == c.id).order_by(Review.id.desc()))
    notes = db.scalars(select(CaseNote).where(CaseNote.customer_id == c.id).order_by(CaseNote.id.desc()))
    docs = db.scalars(select(Document).where(Document.customer_id == c.id).order_by(Document.id))
    return {
        "customer": customer_dict(c),
        "assessments": latest,
        "documents": [document_dict(d) for d in docs],
        "hits": [hit_dict(h) for h in hits],
        "reviews": [review_dict(r) for r in reviews],
        "notes": [note_dict(n) for n in notes],
    }


@router.get("/customers")
def list_customers(
    q: str | None = None,
    risk: str | None = Query(default=None, description="LOW|MEDIUM|HIGH|PROHIBITED|UNRATED"),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Customer).order_by(Customer.id.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.full_name.ilike(like), Customer.customer_ref.ilike(like)))
    if risk == "UNRATED":
        stmt = stmt.where(Customer.risk_rating.is_(None))
    elif risk:
        stmt = stmt.where(Customer.risk_rating == risk)
    if status:
        stmt = stmt.where(Customer.status == status)
    return [customer_dict(c) for c in db.scalars(stmt)]


@router.post("/customers", status_code=201)
def create_customer(
    body: CustomerIn,
    assess: bool = Query(default=True, description="Run the full agent pipeline immediately"),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    c = Customer(customer_ref="TMP-" + uuid.uuid4().hex[:10], **body.model_dump())
    db.add(c)
    db.flush()
    c.customer_ref = f"CUST-{c.id:05d}"
    audit.log(db, actor=user, actor_type=audit.USER, action="CUSTOMER_CREATED", entity_type="customer",
              entity_id=c.id, customer_id=c.id, details={"name": c.full_name})
    db.commit()
    if assess:
        pipeline.run_full_assessment(db, c, actor=user, trigger="ONBOARDING")
    return detail(db, c)


@router.get("/customers/{customer_id}")
def get_customer(c: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db)):
    return detail(db, c)


@router.put("/customers/{customer_id}")
def update_customer(
    body: CustomerUpdate,
    c: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    changes = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        old = getattr(c, k)
        if old != v:
            changes[k] = {"from": str(old), "to": str(v)}
            setattr(c, k, v)
    if changes:
        audit.log(db, actor=user, actor_type=audit.USER, action="CUSTOMER_UPDATED", entity_type="customer",
                  entity_id=c.id, customer_id=c.id, details={"changes": changes})
        db.commit()
    return detail(db, c)


@router.post("/customers/{customer_id}/documents", status_code=201)
def add_document(
    body: DocumentIn,
    c: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    d = Document(customer_id=c.id, **body.model_dump())
    db.add(d)
    db.flush()
    audit.log(db, actor=user, actor_type=audit.USER, action="DOCUMENT_ADDED", entity_type="document",
              entity_id=d.id, customer_id=c.id, details={"doc_type": d.doc_type})
    db.commit()
    return document_dict(d)


@router.post("/customers/{customer_id}/decision")
def decide(
    body: DecisionIn,
    c: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
    role: str = Depends(current_role),
):
    if body.decision == "APPROVE" and c.risk_rating == "HIGH" and role not in CAN["approve_high_risk"]:
        raise HTTPException(403, "HIGH-risk customers must be approved by a Senior Analyst, MLRO or Compliance Manager.")
    if body.decision == "APPROVE" and c.risk_rating == "PROHIBITED":
        raise HTTPException(409, "Customers rated PROHIBITED cannot be approved. Reject or escalate to the MLRO.")
    if body.decision == "APPROVE" and c.risk_rating is None:
        raise HTTPException(409, "Run the AML assessment before approving.")
    if body.decision == "APPROVE" and any(
        h.list_type == "SANCTIONS" and h.disposition == "OPEN" and h.confidence >= 75 for h in c.hits
    ):
        raise HTTPException(409, "Open sanctions matches must be dispositioned before approval.")
    old = c.status
    c.status = DECISION_STATUS[body.decision]
    if body.decision == "APPROVE":
        c.onboarded_at = c.onboarded_at or date.today()
        c.last_kyc_review = c.last_kyc_review or date.today()
        from ..agents.risk import next_review_date

        c.next_review_due = next_review_date(c.risk_rating or "MEDIUM", c.last_kyc_review)
    audit.log(db, actor=user, actor_type=audit.USER, action="CASE_DECISION", entity_type="customer",
              entity_id=c.id, customer_id=c.id,
              details={"decision": body.decision, "note": body.note, "status_from": old, "status_to": c.status,
                       "risk_rating": c.risk_rating})
    db.commit()
    return detail(db, c)


@router.post("/customers/{customer_id}/assess")
def assess(c: Customer = Depends(get_customer_or_404), db: Session = Depends(get_db), user: str = Depends(current_user)):
    audit.log(db, actor=user, actor_type=audit.USER, action="ASSESSMENT_REQUESTED", entity_type="customer",
              entity_id=c.id, customer_id=c.id, details={})
    pipeline.run_full_assessment(db, c, actor=user, trigger="MANUAL")
    return detail(db, c)


@router.post("/customers/{customer_id}/agents/{agent}")
def run_one_agent(
    agent: str,
    c: Customer = Depends(get_customer_or_404),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    if agent not in pipeline.ORDER:
        raise HTTPException(404, f"Unknown agent '{agent}'. Valid: {pipeline.ORDER}")
    pipeline.run_single(db, c, agent, actor=user)
    return detail(db, c)
