from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..auth import CAN
from ..deps import current_user, require_role
from ..models import Alert, Customer, Sar, TravelRuleTransfer
from ..modules import sar as sarsvc
from ..modules.alerts import OPEN_STATUSES

router = APIRouter(prefix="/api", tags=["alerts-mlro"])


class AlertAction(BaseModel):
    action: str = Field(pattern="^(ASSIGN|START_REVIEW|CLOSE|ESCALATE)$")
    note: str | None = None
    assignee: str | None = None


class MlroDecision(BaseModel):
    decision: str = Field(pattern="^(FILE_SAR|CLOSE_NO_SAR|REQUEST_MORE_INFO|EXIT_RELATIONSHIP)$")
    rationale: str = Field(min_length=10)


def aware(t):
    return t if t is None or t.tzinfo else t.replace(tzinfo=timezone.utc)


def alert_dict(a: Alert) -> dict:
    return dict(id=a.id, source=a.source, entity_type=a.entity_type, entity_id=a.entity_id, customer_id=a.customer_id, severity=a.severity, title=a.title,
                description=a.description, details=a.details, status=a.status, assigned_to=a.assigned_to, sar_id=a.sar_id, resolution=a.resolution,
                created_at=a.created_at.isoformat(), escalated_at=a.escalated_at.isoformat() if a.escalated_at else None,
                closed_at=a.closed_at.isoformat() if a.closed_at else None)


@router.get("/alerts")
def list_alerts(status: str | None = None, source: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(Alert.id.desc())
    if status:
        stmt = stmt.where(Alert.status == status)
    if source:
        stmt = stmt.where(Alert.source == source)
    return [alert_dict(a) for a in db.scalars(stmt)]


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    return alert_dict(a)


@router.post("/alerts/{alert_id}/action")
def alert_action(alert_id: int, body: AlertAction, db: Session = Depends(get_db), user: str = Depends(current_user)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if a.status == "CLOSED":
        raise HTTPException(409, "Alert is closed")
    if a.status in ("ESCALATED_MLRO", "SAR_DRAFTED"):
        raise HTTPException(409, f"Alert is {a.status}; only the MLRO can act on it.")
    old = a.status
    if body.action == "ASSIGN":
        a.assigned_to = body.assignee or user
    elif body.action == "START_REVIEW":
        a.status, a.assigned_to = "IN_REVIEW", a.assigned_to or user
    elif body.action == "CLOSE":
        if not body.note or len(body.note.strip()) < 10:
            raise HTTPException(422, "Closing an alert requires a rationale of at least 10 characters.")
        a.status, a.resolution, a.closed_at = "CLOSED", body.note.strip(), datetime.now(timezone.utc)
    elif body.action == "ESCALATE":
        if not body.note or len(body.note.strip()) < 10:
            raise HTTPException(422, "Escalation requires a rationale of at least 10 characters.")
        a.status, a.escalated_at, a.resolution = "ESCALATED_MLRO", datetime.now(timezone.utc), body.note.strip()
    audit.log(db, actor=user, actor_type=audit.USER, action="ALERT_ACTION", entity_type="alert", entity_id=a.id, customer_id=a.customer_id,
              details=dict(action=body.action, note=body.note, status_from=old, status_to=a.status, priority=a.severity))
    db.commit()
    return alert_dict(a)


@router.post("/mlro/alerts/{alert_id}/decision")
def mlro_decision(alert_id: int, body: MlroDecision, db: Session = Depends(get_db), user: str = Depends(current_user), _: str = Depends(require_role(*CAN["mlro_decision"]))):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    if a.status != "ESCALATED_MLRO":
        raise HTTPException(409, f"Alert must be ESCALATED_MLRO (is {a.status}).")
    sar = None
    if body.decision == "FILE_SAR":
        stype, sid = {"customer": ("customer", a.entity_id), "corporate": ("corporate", a.entity_id), "wallet": ("wallet", a.entity_id)}.get(
            a.entity_type, ("customer", a.customer_id) if a.customer_id else (None, None))
        if stype is None:
            raise HTTPException(409, "Cannot determine SAR subject for this alert.")
        sar = sarsvc.generate(db, stype, sid, actor=user, alert_id=a.id)
        a.status, a.sar_id = "SAR_DRAFTED", sar.id
    elif body.decision == "CLOSE_NO_SAR":
        a.status, a.closed_at = "CLOSED", datetime.now(timezone.utc)
    elif body.decision == "REQUEST_MORE_INFO":
        a.status = "IN_REVIEW"
    elif body.decision == "EXIT_RELATIONSHIP":
        a.status, a.closed_at = "CLOSED", datetime.now(timezone.utc)
        if a.customer_id and (c := db.get(Customer, a.customer_id)):
            c.status = "EXITED"
    a.resolution = f"MLRO {body.decision}: {body.rationale}"
    audit.log(db, actor=user, actor_type=audit.USER, action="MLRO_DECISION", entity_type="alert", entity_id=a.id, customer_id=a.customer_id,
              details=dict(decision=body.decision, rationale=body.rationale, sar_id=sar.id if sar else None, priority=a.severity))
    db.commit()
    return dict(alert=alert_dict(a), sar_id=sar.id if sar else None)


@router.get("/mlro/dashboard")
def mlro_dashboard(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    alerts = list(db.scalars(select(Alert)))
    sars = list(db.scalars(select(Sar)))
    open_a = [a for a in alerts if a.status in OPEN_STATUSES]
    queue = [a for a in alerts if a.status == "ESCALATED_MLRO"]
    age = lambda a: (now - aware(a.created_at)).days
    pending_sars = [s for s in sars if s.status == "PENDING_MLRO"]
    transfers = list(db.scalars(select(TravelRuleTransfer)))
    customers = list(db.scalars(select(Customer)))
    return dict(
        kpis=dict(open_alerts=len(open_a), escalated_to_mlro=len(queue), critical_open=sum(a.severity == "CRITICAL" for a in open_a),
                  sars_pending_approval=len(pending_sars), sars_draft=sum(s.status == "DRAFT" for s in sars),
                  sars_filed=sum(s.status == "FILED" for s in sars), sars_rejected=sum(s.status == "REJECTED" for s in sars),
                  travel_rule_holds=sum(t.status in ("HOLD_REQUEST_INFO", "REJECT") for t in transfers),
                  high_risk_customers=sum(c.risk_rating in ("HIGH", "PROHIBITED") for c in customers)),
        alerts_by_source=dict(Counter(a.source for a in open_a)), alerts_by_severity=dict(Counter(a.severity for a in open_a)),
        alerts_by_status=dict(Counter(a.status for a in alerts)),
        escalation_queue=[dict(alert_dict(a), age_days=age(a)) for a in sorted(queue, key=lambda x: ({"CRITICAL": 0, "HIGH": 1}.get(x.severity, 2), x.id))],
        sar_approval_queue=[dict(id=s.id, reference=s.reference, subject_name=s.subject_name, total_amount_eur=s.total_amount_eur, typologies=s.typologies,
                                 prepared_by=s.prepared_by, submitted_at=s.submitted_at.isoformat() if s.submitted_at else None) for s in pending_sars],
        oldest_open_alert_days=max((age(a) for a in open_a), default=0),
    )
