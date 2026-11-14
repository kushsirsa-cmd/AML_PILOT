from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..auth import CAN
from ..deps import current_user, require_role
from ..models import RegulatoryReport
from ..modules import reporting as rp

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateIn(BaseModel):
    report_type: str
    period_start: date | None = None
    period_end: date | None = None


def get_report(rid: int, db: Session) -> RegulatoryReport:
    r = db.get(RegulatoryReport, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/types")
def types():
    return rp.REPORT_TYPES


@router.get("")
def list_reports(db: Session = Depends(get_db)):
    return [rp.report_dict(r) for r in db.scalars(select(RegulatoryReport).order_by(RegulatoryReport.id.desc()))]


@router.post("/generate", status_code=201)
def generate(body: GenerateIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    end = body.period_end or date.today()
    start = body.period_start or end - timedelta(days=90)
    try:
        r = rp.generate(db, body.report_type, start, end, actor=user)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit.log(db, actor=user, actor_type=audit.USER, action="REPORT_GENERATED", entity_type="report", entity_id=r.id, details=dict(type=r.report_type, start=str(start), end=str(end)))
    db.commit()
    return rp.report_dict(r, full=True)


@router.get("/{rid}")
def detail(rid: int, db: Session = Depends(get_db)):
    return rp.report_dict(get_report(rid, db), full=True)


@router.post("/{rid}/approve")
def approve(rid: int, db: Session = Depends(get_db), user: str = Depends(current_user), _: str = Depends(require_role(*CAN["report_approve"]))):
    r = get_report(rid, db)
    if r.status != "DRAFT":
        raise HTTPException(409, f"Only DRAFT reports can be approved (is {r.status}).")
    if user.strip().lower() == r.generated_by.strip().lower():
        raise HTTPException(403, "Four-eyes control: the report generator cannot approve their own report.")
    r.status, r.approved_by, r.approved_at = "APPROVED", user, datetime.now(timezone.utc)
    audit.log(db, actor=user, actor_type=audit.USER, action="REPORT_APPROVED", entity_type="report", entity_id=r.id, details=dict(type=r.report_type))
    db.commit()
    return rp.report_dict(r)


@router.post("/{rid}/submit")
def submit(rid: int, db: Session = Depends(get_db), user: str = Depends(current_user), _: str = Depends(require_role(*CAN["report_approve"]))):
    r = get_report(rid, db)
    if r.status != "APPROVED":
        raise HTTPException(409, f"Only APPROVED reports can be submitted (is {r.status}).")
    r.status, r.submitted_at = "SUBMITTED", datetime.now(timezone.utc)
    r.submission_reference = f"REG-SIM-{r.submitted_at:%Y%m%d}-{r.id:04d}"
    audit.log(db, actor=user, actor_type=audit.USER, action="REPORT_SUBMITTED", entity_type="report", entity_id=r.id,
              details=dict(type=r.report_type, reference=r.submission_reference, simulated=True))
    db.commit()
    return rp.report_dict(r)


@router.get("/{rid}/csv")
def csv_export(rid: int, db: Session = Depends(get_db)):
    r = get_report(rid, db)
    return Response(rp.to_csv(r), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{r.report_type}_{r.period_end}.csv"'})
