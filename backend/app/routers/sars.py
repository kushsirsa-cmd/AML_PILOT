from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..auth import CAN
from ..deps import current_user, require_role
from ..models import Alert, Sar
from ..modules import sar as sarsvc

router = APIRouter(prefix="/api/sars", tags=["sar"])


class GenerateIn(BaseModel):
    subject_type: str = Field(pattern="^(customer|corporate|wallet)$")
    subject_id: int
    alert_id: int | None = None


class NarrativeIn(BaseModel):
    narrative: str = Field(min_length=50)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: str = Field(min_length=5)


def sdict(s: Sar, full: bool = False) -> dict:
    d = dict(id=s.id, reference=s.reference, subject_type=s.subject_type, subject_id=s.subject_id, subject_name=s.subject_name, customer_id=s.customer_id,
             alert_id=s.alert_id, status=s.status, typologies=s.typologies, total_amount_eur=s.total_amount_eur, engine=s.engine, prepared_by=s.prepared_by,
             approved_by=s.approved_by, mlro_note=s.mlro_note, filing_reference=s.filing_reference, created_at=s.created_at.isoformat(),
             submitted_at=s.submitted_at.isoformat() if s.submitted_at else None, decided_at=s.decided_at.isoformat() if s.decided_at else None)
    if full:
        d["narrative"], d["evidence"] = s.narrative, s.evidence
        d["narrative_gaps"] = sarsvc.narrative_gaps(s.narrative)
    return d


def get_sar(sar_id: int, db: Session) -> Sar:
    s = db.get(Sar, sar_id)
    if not s:
        raise HTTPException(404, "SAR not found")
    return s


@router.get("")
def list_sars(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Sar).order_by(Sar.id.desc())
    if status:
        stmt = stmt.where(Sar.status == status)
    return [sdict(s) for s in db.scalars(stmt)]


@router.post("/generate", status_code=201)
def generate(body: GenerateIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    try:
        s = sarsvc.generate(db, body.subject_type, body.subject_id, actor=user, alert_id=body.alert_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.commit()
    return sdict(s, full=True)


@router.get("/{sar_id}")
def detail(sar_id: int, db: Session = Depends(get_db)):
    return sdict(get_sar(sar_id, db), full=True)


@router.put("/{sar_id}/narrative")
def edit(sar_id: int, body: NarrativeIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    s = get_sar(sar_id, db)
    if s.status != "DRAFT":
        raise HTTPException(409, f"Only DRAFT SARs can be edited (is {s.status}).")
    s.narrative = body.narrative
    s.engine = f"{s.engine}+edited"
    audit.log(db, actor=user, actor_type=audit.USER, action="SAR_NARRATIVE_EDITED", entity_type="sar", entity_id=s.id, customer_id=s.customer_id, details={"chars": len(body.narrative)})
    db.commit()
    return sdict(s, full=True)


@router.post("/{sar_id}/submit")
def submit(sar_id: int, db: Session = Depends(get_db), user: str = Depends(current_user)):
    s = get_sar(sar_id, db)
    if s.status != "DRAFT":
        raise HTTPException(409, f"Only DRAFT SARs can be submitted (is {s.status}).")
    gaps = sarsvc.narrative_gaps(s.narrative)
    if gaps:
        raise HTTPException(422, "Narrative is missing required sections: " + ", ".join(gaps))
    s.status, s.submitted_at = "PENDING_MLRO", datetime.now(timezone.utc)
    audit.log(db, actor=user, actor_type=audit.USER, action="SAR_SUBMITTED", entity_type="sar", entity_id=s.id, customer_id=s.customer_id, details={"reference": s.reference})
    db.commit()
    return sdict(s)


@router.post("/{sar_id}/decision")
def decide(sar_id: int, body: DecisionIn, db: Session = Depends(get_db), user: str = Depends(current_user), _: str = Depends(require_role(*CAN["mlro_decision"]))):
    s = get_sar(sar_id, db)
    if s.status != "PENDING_MLRO":
        raise HTTPException(409, f"SAR must be PENDING_MLRO (is {s.status}).")
    if user.strip().lower() == s.prepared_by.strip().lower():
        raise HTTPException(403, "Four-eyes control: the SAR preparer cannot approve or reject their own SAR.")
    s.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    s.approved_by, s.mlro_note, s.decided_at = user, body.note, datetime.now(timezone.utc)
    if s.status == "REJECTED":
        s.status = "REJECTED"
    audit.log(db, actor=user, actor_type=audit.USER, action="SAR_MLRO_DECISION", entity_type="sar", entity_id=s.id, customer_id=s.customer_id,
              details=dict(decision=body.decision, note=body.note, reference=s.reference, priority="CRITICAL"))
    db.commit()
    return sdict(s)


@router.post("/{sar_id}/file")
def file(sar_id: int, db: Session = Depends(get_db), user: str = Depends(current_user), _: str = Depends(require_role(*CAN["mlro_decision"]))):
    s = get_sar(sar_id, db)
    if s.status != "APPROVED":
        raise HTTPException(409, f"Only APPROVED SARs can be filed (is {s.status}).")
    s.status = "FILED"
    s.filing_reference = f"FIU-SIM-{datetime.now(timezone.utc):%Y%m%d}-{s.id:04d}"
    if s.alert_id and (a := db.get(Alert, s.alert_id)):
        a.status, a.closed_at = "CLOSED", datetime.now(timezone.utc)
        a.resolution = f"SAR {s.reference} filed ({s.filing_reference})"
    audit.log(db, actor=user, actor_type=audit.USER, action="SAR_FILED", entity_type="sar", entity_id=s.id, customer_id=s.customer_id,
              details=dict(filing_reference=s.filing_reference, simulated=True))
    db.commit()
    return sdict(s)


@router.get("/{sar_id}/xml")
def xml(sar_id: int, db: Session = Depends(get_db)):
    s = get_sar(sar_id, db)
    return Response(sarsvc.to_xml(s), media_type="application/xml", headers={"Content-Disposition": f'attachment; filename="{s.reference}.xml"'})
