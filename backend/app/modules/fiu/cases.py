"""CASE MANAGEMENT - lifecycle, queues, permissions, four-eyes, alert sync, audit.

Queues: ALERT (virtual - open alerts with no case yet) -> TRIAGE -> FIU -> ESCALATION -> SAR -> MLRO -> CLOSED.
The SAR / MLRO stages are driven by the existing SAR workflow (Sar.status) so there is one source of truth for approvals."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import audit
from ...auth import CAN
from ...models import Alert, Investigation, Sar, User
from .. import sar as sarsvc
from . import crypto_investigation, fiu_agent, investigator, rbi, sar_agent, typology
from .common import level, load_entity, name_of, ref_of
from .investigator import DISPOSITIONS, subject_of_alert
from .links import build_index

QUEUES = ["TRIAGE", "FIU", "ESCALATION", "SAR", "MLRO"]
QUEUE_STEP = {"TRIAGE": 2, "FIU": 5, "ESCALATION": 7, "SAR": 8, "MLRO": 8, "CLOSED": 9}
HIGH = {"HIGH", "CRITICAL"}


class CaseError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def role_of(db: Session, username: str) -> str:
    u = db.scalar(select(User).where(User.username == username))
    return u.role if u else "ANALYST"


def note(inv: Investigation, author: str, text: str, kind: str = "NOTE") -> None:
    inv.notes = list(inv.notes or []) + [dict(ts=_now().isoformat(), author=author, text=text, kind=kind)]


def _log(db: Session, user: str, action: str, inv: Investigation, **details) -> None:
    audit.log(db, actor=user, actor_type=audit.USER, action=action, entity_type="investigation", entity_id=inv.id, customer_id=inv.customer_id,
              details=dict(reference=inv.reference, queue=inv.queue, **details))


def _move(inv: Investigation, queue: str) -> None:
    inv.queue, inv.step = queue, QUEUE_STEP[queue]


def _sync_alert(db: Session, inv: Investigation, status: str, resolution: str | None = None) -> None:
    if inv.alert_id and (a := db.get(Alert, inv.alert_id)):
        a.status = status
        if status == "CLOSED":
            a.closed_at, a.resolution = _now(), resolution
        if status == "ESCALATED_MLRO" and not a.escalated_at:
            a.escalated_at = _now()
        if inv.sar_id:
            a.sar_id = inv.sar_id


def run_agents(db: Session, inv: Investigation, idx=None) -> dict:
    """Run every agent for the case subject and cache their output on the case. Rules-engine only; no decisions are taken."""
    idx = idx or build_index(db)
    et, eid = inv.entity_type, inv.entity_id
    det = typology.detect(db, et, eid, idx)
    rb = rbi.build(db, et, eid, idx=idx, det=det)
    fiu = fiu_agent.investigate(db, et, eid, idx=idx, rbi_conf=rb["confidence"]["score"], mitigating=rb["mitigating_facts"])
    alert = db.get(Alert, inv.alert_id) if inv.alert_id else None
    wb = investigator.prepare(db, et, eid, alert, inv.step, fiu["typology"], rb, fiu)
    crypto = crypto_investigation.investigate_entity(db, et, eid)
    inv.confidence, inv.risk_score = rb["confidence"]["score"], max(fiu["typology"]["risk_score"], fiu["network"]["network_risk"]["score"] if fiu["network"].get("linked") else 0)
    inv.typologies = [d["code"] for d in fiu["typology"]["detections"]]
    inv.agents = dict(rbi=rb, fiu=fiu, workbook=wb, crypto=crypto, ran_at=_now().isoformat())
    return inv.agents


def open_case(db: Session, user: str, *, alert_id: int | None = None, entity_type: str | None = None, entity_id: int | None = None, source_type: str | None = None, title: str | None = None) -> Investigation:
    alert = None
    if alert_id:
        alert = db.get(Alert, alert_id)
        if not alert:
            raise CaseError(404, "Alert not found")
        dup = db.scalar(select(Investigation).where(Investigation.alert_id == alert_id, Investigation.queue != "CLOSED"))
        if dup:
            raise CaseError(409, f"Alert already has an open investigation ({dup.reference}).")
        subj = subject_of_alert(db, alert)
        if not subj:
            raise CaseError(422, "Alert has no customer or corporate subject to investigate.")
        entity_type, entity_id = subj
    if entity_type not in ("customer", "corporate") or not entity_id:
        raise CaseError(422, "Provide an alert_id, or entity_type (customer|corporate) and entity_id.")
    try:
        obj = load_entity(db, entity_type, entity_id)
    except Exception as exc:
        raise CaseError(404, "Entity not found") from exc
    inv = Investigation(reference="PENDING", title=title or (alert.title if alert else f"Investigation - {name_of(obj)}"), source_type=source_type or ("ALERT" if alert else "MANUAL"),
                        alert_id=alert_id, entity_type=entity_type, entity_id=entity_id, customer_id=entity_id if entity_type == "customer" else None,
                        priority=alert.severity if alert else "MEDIUM", queue="TRIAGE", step=2, opened_by=user, assigned_to=user)
    db.add(inv)
    db.flush()
    inv.reference = f"INV-{_now().year}-{inv.id:04d}"
    run_agents(db, inv)
    inv.priority = inv.agents["rbi"]["priority"]["level"] if not alert else max([alert.severity, inv.agents["rbi"]["priority"]["level"]], key=["LOW", "MEDIUM", "HIGH", "CRITICAL"].index)
    note(inv, "AML Investigations agent", f"Case opened from {inv.source_type.lower()}. Workbook prepared (confidence {inv.confidence}/100). Awaiting triage decision.", "AGENT")
    _sync_alert(db, inv, "IN_REVIEW")
    _log(db, user, "INVESTIGATION_OPENED", inv, source=inv.source_type, alert_id=alert_id)
    return inv


def _need(db: Session, user: str, action: str) -> str:
    role = role_of(db, user)
    if role not in CAN[action]:
        raise CaseError(403, f"Your role ({role}) cannot do this. Required: {' / '.join(sorted(CAN[action]))}.")
    return role


def sync(db: Session, inv: Investigation) -> None:
    """Pull SAR workflow state into the case (single source of truth for approvals)."""
    if not inv.sar_id or inv.queue == "CLOSED":
        return
    s = db.get(Sar, inv.sar_id)
    if not s:
        return
    if s.status == "DRAFT" and inv.queue != "SAR":
        _move(inv, "SAR")
    elif s.status in ("PENDING_MLRO", "APPROVED") and inv.queue != "MLRO":
        _move(inv, "MLRO"); _sync_alert(db, inv, "ESCALATED_MLRO")
    elif s.status == "REJECTED" and inv.queue in ("SAR", "MLRO"):
        _move(inv, "FIU"); note(inv, "system", f"MLRO rejected {s.reference}: {s.mlro_note}. Returned to the FIU queue.", "SYSTEM"); inv.sar_id = None
    elif s.status == "FILED":
        inv.disposition, inv.closure_rationale = "SAR_FILED", f"{s.reference} filed ({s.filing_reference})"
        inv.closed_at = _now(); _move(inv, "CLOSED"); _sync_alert(db, inv, "CLOSED", inv.closure_rationale)


def act(db: Session, user: str, inv: Investigation, action: str, text: str | None = None, disposition: str | None = None, assignee: str | None = None) -> Investigation:
    sync(db, inv)
    if inv.queue == "CLOSED" and action != "reopen":
        raise CaseError(409, "Case is closed.")
    role = role_of(db, user)
    if action == "accept_to_fiu":
        if inv.queue != "TRIAGE":
            raise CaseError(409, f"Case must be in TRIAGE (is {inv.queue}).")
        _move(inv, "FIU"); note(inv, user, text or "Triage complete - accepted for FIU investigation.", "DECISION")
    elif action == "escalate":
        if inv.queue != "FIU":
            raise CaseError(409, f"Only FIU-queue cases can be escalated (is {inv.queue}).")
        _need(db, user, "approve_high_risk")
        if not text or len(text) < 10:
            raise CaseError(422, "Escalation needs a rationale (min 10 characters).")
        inv.escalated_by = user; _move(inv, "ESCALATION"); note(inv, user, text, "DECISION")
    elif action == "to_sar":
        if inv.queue != "ESCALATION":
            raise CaseError(409, f"Case must be in ESCALATION (is {inv.queue}).")
        _need(db, user, "approve_high_risk")
        s = sarsvc.generate(db, inv.entity_type, inv.entity_id, actor=user, alert_id=inv.alert_id)
        db.flush()
        inv.sar_id = s.id; _move(inv, "SAR"); note(inv, user, text or f"SAR {s.reference} drafted for MLRO review.", "DECISION")
        _sync_alert(db, inv, "SAR_DRAFTED")
    elif action == "return_to_triage":
        if inv.queue not in ("FIU", "ESCALATION"):
            raise CaseError(409, "Only FIU / ESCALATION cases can go back.")
        _move(inv, "TRIAGE"); note(inv, user, text or "Returned to triage.", "DECISION")
    elif action == "close":
        if disposition not in DISPOSITIONS or disposition == "SAR_FILED":
            raise CaseError(422, "Choose a disposition: " + ", ".join(k for k in DISPOSITIONS if k != "SAR_FILED") + ". (SAR_FILED is set when the MLRO files the SAR.)")
        if not text or len(text) < 15:
            raise CaseError(422, "Closure needs a rationale (min 15 characters).")
        if inv.sar_id:
            s = db.get(Sar, inv.sar_id)
            if s and s.status in ("PENDING_MLRO", "APPROVED"):
                raise CaseError(409, "A SAR is with the MLRO - resolve it there first.")
        if inv.queue in ("ESCALATION", "SAR", "MLRO") or disposition in ("SUSPICION_NO_SAR", "EXIT_RELATIONSHIP") or inv.priority in HIGH:
            _need(db, user, "approve_high_risk")
        if inv.queue in ("ESCALATION", "SAR", "MLRO") or disposition == "SUSPICION_NO_SAR":
            _need(db, user, "mlro_decision")  # a no-report decision on an escalated / suspicious case is the MLRO's
        if inv.priority in HIGH and inv.assigned_to and inv.assigned_to == user and role != "MLRO":
            raise CaseError(403, "Four-eyes control: the investigator who worked a HIGH / CRITICAL case cannot close it. Another authorised reviewer must.")
        inv.disposition, inv.closure_rationale, inv.closed_at = disposition, text, _now()
        _move(inv, "CLOSED"); note(inv, user, f"Closed - {disposition}: {text}", "DECISION")
        _sync_alert(db, inv, "CLOSED", f"{disposition}: {text}")
    elif action == "assign":
        inv.assigned_to = assignee or user; note(inv, user, f"Assigned to {inv.assigned_to}.", "SYSTEM")
    elif action == "note":
        if not text:
            raise CaseError(422, "Note text required.")
        note(inv, user, text)
    elif action == "refresh":
        run_agents(db, inv); note(inv, user, "Agents re-run on latest data.", "SYSTEM")
    elif action == "reopen":
        _need(db, user, "mlro_decision")
        if inv.queue != "CLOSED" or inv.disposition == "SAR_FILED":
            raise CaseError(409, "Only closed cases without a filed SAR can be reopened.")
        inv.closed_at = None; inv.disposition = None; _move(inv, "FIU"); note(inv, user, text or "Reopened.", "DECISION"); _sync_alert(db, inv, "IN_REVIEW")
    else:
        raise CaseError(422, f"Unknown action '{action}'.")
    _log(db, user, f"INVESTIGATION_{action.upper()}", inv, disposition=disposition, text=(text or "")[:200])
    return inv


def summary(db: Session, inv: Investigation) -> dict:
    ag = inv.agents or {}
    obj = load_entity(db, inv.entity_type, inv.entity_id)
    return dict(id=inv.id, reference=inv.reference, title=inv.title, source_type=inv.source_type, alert_id=inv.alert_id, entity_type=inv.entity_type, entity_id=inv.entity_id,
                subject=name_of(obj), subject_ref=ref_of(obj), rating=getattr(obj, "risk_rating", None), priority=inv.priority, queue=inv.queue, step=inv.step, assigned_to=inv.assigned_to,
                opened_by=inv.opened_by, confidence=inv.confidence, risk_score=inv.risk_score, typologies=inv.typologies, disposition=inv.disposition, sar_id=inv.sar_id,
                created_at=inv.created_at.isoformat(), updated_at=inv.updated_at.isoformat() if inv.updated_at else None,
                age_days=(_now() - (inv.created_at if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=timezone.utc))).days, notes_count=len(inv.notes or []),
                sar_recommendation=(ag.get("fiu", {}).get("sar_recommendation") or {}).get("recommendation"))


def alert_queue(db: Session, limit: int = 50) -> list[dict]:
    open_inv = {i for i in db.scalars(select(Investigation.alert_id).where(Investigation.alert_id.is_not(None), Investigation.queue != "CLOSED"))}
    rows = db.scalars(select(Alert).where(Alert.status == "OPEN").order_by(Alert.created_at.desc())).all()
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows = sorted([a for a in rows if a.id not in open_inv], key=lambda a: (rank.get(a.severity, 9), -a.id))[:limit]
    return [dict(id=a.id, source=a.source, severity=a.severity, title=a.title, entity_type=a.entity_type, entity_id=a.entity_id, created_at=a.created_at.isoformat()) for a in rows]
