"""Investigations & FIU API: dashboard, case queues + lifecycle, RBI, typology, network, crypto investigation, SAR formats, operating model."""
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import CAN
from ..db import get_db
from ..deps import current_role, current_user
from ..models import Corporate, Customer, Investigation, Sar, Transaction, Wallet
from ..modules.fiu import cases, crypto_investigation, network, operating_model, rbi, sar_agent, typology
from ..modules.fiu.common import level
from ..modules.fiu.links import build_index

router = APIRouter(prefix="/api", tags=["investigations-fiu"])


class OpenIn(BaseModel):
    alert_id: int | None = None
    entity_type: str | None = Field(default=None, pattern="^(customer|corporate)$")
    entity_id: int | None = None
    source_type: str | None = Field(default=None, pattern="^(ALERT|RBI|FIU|MANUAL)$")
    title: str | None = None


class ActIn(BaseModel):
    action: str
    text: str | None = None
    disposition: str | None = None
    assignee: str | None = None


def _get(db: Session, iid: int) -> Investigation:
    inv = db.get(Investigation, iid)
    if not inv:
        raise HTTPException(404, "Investigation not found")
    return inv


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except cases.CaseError as e:
        raise HTTPException(e.status, e.msg) from e


@router.get("/fiu/dashboard")
def dashboard(db: Session = Depends(get_db)):
    invs = list(db.scalars(select(Investigation)))
    for i in invs:
        cases.sync(db, i)
    openi = [i for i in invs if i.queue != "CLOSED"]
    q = Counter(i.queue for i in invs)
    sars = list(db.scalars(select(Sar)))
    cl = network.clusters(db, min_score=35)
    hr_c = db.scalar(select(func.count()).select_from(Customer).where(Customer.risk_rating.in_(["HIGH", "PROHIBITED"]))) or 0
    hr_k = db.scalar(select(func.count()).select_from(Corporate).where(Corporate.risk_rating.in_(["HIGH", "PROHIBITED"]))) or 0
    hr_w = db.scalar(select(func.count()).select_from(Wallet).where(Wallet.risk_level.in_(["HIGH", "SEVERE"]))) or 0
    susp = [t for t in db.scalars(select(Transaction)) if t.flags]
    ages = Counter()
    for i in openi:
        d = cases.summary(db, i)["age_days"]
        ages["0-7d" if d <= 7 else "8-30d" if d <= 30 else "31d+"] += 1
    ty = Counter(t for i in openi for t in (i.typologies or []))
    db.commit()
    return dict(
        tiles=dict(open_investigations=len(openi), pending_escalations=q.get("ESCALATION", 0), sar_queue=q.get("SAR", 0) + q.get("MLRO", 0),
                   high_risk_customers=hr_c + hr_k, high_risk_wallets=hr_w, suspicious_transactions=len(susp),
                   suspicious_transactions_eur=round(sum(t.amount_eur for t in susp)), network_cases=len(cl),
                   regulatory_filing_queue=sum(1 for s in sars if s.status in ("PENDING_MLRO", "APPROVED"))),
        queues={k: q.get(k, 0) for k in cases.QUEUES + ["CLOSED"]}, priority=dict(Counter(i.priority for i in openi)), ageing=dict(ages),
        typologies=[dict(code=k, label=typology.TYPOLOGIES.get(k, (k, ""))[0], count=v) for k, v in ty.most_common()],
        disposition=dict(Counter(i.disposition for i in invs if i.disposition)),
        filing=dict(draft=sum(1 for s in sars if s.status == "DRAFT"), pending_mlro=sum(1 for s in sars if s.status == "PENDING_MLRO"), approved=sum(1 for s in sars if s.status == "APPROVED"), filed=sum(1 for s in sars if s.status == "FILED")),
        top_clusters=[dict(id=c["id"], size=c["size"], score=c["score"], level=c["level"], names=[m["name"] for m in c["members"]][:3]) for c in cl[:5]],
        rbi_queue=rbi.queue(db, limit=6))


@router.get("/investigations")
def list_cases(queue: str | None = None, db: Session = Depends(get_db)):
    invs = list(db.scalars(select(Investigation).order_by(Investigation.id.desc())))
    for i in invs:
        cases.sync(db, i)
    db.commit()
    counts = Counter(i.queue for i in invs)
    rows = [cases.summary(db, i) for i in invs if (not queue or i.queue == queue)]
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows.sort(key=lambda r: (rank.get(r["priority"], 9), -(r["risk_score"] or 0)))
    out = dict(counts={**{k: counts.get(k, 0) for k in cases.QUEUES + ["CLOSED"]}, "ALERT": len(cases.alert_queue(db, 500))}, items=rows)
    if queue == "ALERT":
        out["items"] = cases.alert_queue(db)
    return out


@router.post("/investigations", status_code=201)
def open_case(body: OpenIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    inv = _wrap(cases.open_case, db, user, alert_id=body.alert_id, entity_type=body.entity_type, entity_id=body.entity_id, source_type=body.source_type, title=body.title)
    db.commit()
    return cases.summary(db, inv)


@router.get("/investigations/{iid}")
def detail(iid: int, db: Session = Depends(get_db), role: str = Depends(current_role)):
    inv = _get(db, iid)
    cases.sync(db, inv)
    db.commit()
    ag = inv.agents or {}
    sar = db.get(Sar, inv.sar_id) if inv.sar_id else None
    formats = sar_agent.build(ag["fiu"], ag.get("rbi"), inv, db, reference=sar.reference if sar else None) if ag.get("fiu") else None
    can = dict(accept_to_fiu=inv.queue == "TRIAGE", escalate=inv.queue == "FIU" and role in CAN["approve_high_risk"], to_sar=inv.queue == "ESCALATION" and role in CAN["approve_high_risk"],
               close=inv.queue != "CLOSED" and role in CAN["approve_high_risk"] or (inv.queue == "TRIAGE" and inv.priority not in cases.HIGH), mlro=role in CAN["mlro_decision"])
    # re-label workbook step status for the current step
    wb = ag.get("workbook")
    if wb:
        for s in wb["steps"]:
            s["status"] = "DONE" if s["n"] < inv.step or inv.queue == "CLOSED" else "CURRENT" if s["n"] == inv.step else "PENDING"
    return dict(summary=cases.summary(db, inv), notes=inv.notes or [], closure_rationale=inv.closure_rationale, agents=ag, sar=dict(id=sar.id, reference=sar.reference, status=sar.status) if sar else None,
                sar_package=formats, can=can, role=role, dispositions=cases.DISPOSITIONS)


@router.post("/investigations/{iid}/actions")
def action(iid: int, body: ActIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    inv = _get(db, iid)
    _wrap(cases.act, db, user, inv, body.action, body.text, body.disposition, body.assignee)
    db.commit()
    return cases.summary(db, inv)


@router.get("/investigations/{iid}/report/{fmt}", response_class=PlainTextResponse)
def report(iid: int, fmt: str, db: Session = Depends(get_db)):
    inv = _get(db, iid)
    ag = inv.agents or {}
    if fmt not in sar_agent.FORMATS or not ag.get("fiu"):
        raise HTTPException(404, "Unknown format")
    r = sar_agent.build(ag["fiu"], ag.get("rbi"), inv, db)["formats"][fmt]
    lines = [r["label"].upper(), "=" * len(r["label"]), r["disclaimer"], "", f"Destination: {r['destination_note']}", ""]
    for k, v in r["sections"]:
        lines += [f"## {k}", str(v), ""]
    return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": f'attachment; filename="{inv.reference}-{fmt}.txt"'})


@router.get("/rbi/queue")
def rbi_queue(db: Session = Depends(get_db)):
    return rbi.queue(db)


@router.get("/rbi/{etype}/{eid}")
def rbi_report(etype: str, eid: int, db: Session = Depends(get_db)):
    _check(etype)
    return rbi.build(db, etype, eid)


@router.get("/typology/{etype}/{eid}")
def typology_report(etype: str, eid: int, db: Session = Depends(get_db)):
    _check(etype)
    return typology.detect(db, etype, eid)


@router.get("/network/clusters")
def net_clusters(min_score: int = 0, db: Session = Depends(get_db)):
    return network.clusters(db, min_score=min_score)


@router.get("/network/{etype}/{eid}")
def net_entity(etype: str, eid: int, hops: int = 2, db: Session = Depends(get_db)):
    _check(etype)
    return network.analyze(db, etype, eid, hops=max(1, min(hops, 3)))


@router.get("/crypto-investigation/wallet/{wid}")
def crypto_wallet(wid: int, db: Session = Depends(get_db)):
    w = db.get(Wallet, wid)
    if not w:
        raise HTTPException(404, "Wallet not found")
    return crypto_investigation.investigate_wallet(db, w)


@router.get("/crypto-investigation/{etype}/{eid}")
def crypto_entity(etype: str, eid: int, db: Session = Depends(get_db)):
    _check(etype)
    return crypto_investigation.investigate_entity(db, etype, eid)


class OMIn(BaseModel):
    adoption: float = Field(default=0.7, ge=0, le=1)
    optional: list[str] = []
    fte: dict[str, float] = {}
    regulators: list[str] = []


@router.get("/operating-model")
def om_default():
    return operating_model.calculate()


@router.post("/operating-model/calculate")
def om_calc(body: OMIn):
    for k, v in body.fte.items():
        if v < 0 or v > 5000:
            raise HTTPException(422, f"FTE for {k} out of range")
    return operating_model.calculate(body.model_dump())


def _check(etype: str) -> None:
    if etype not in ("customer", "corporate"):
        raise HTTPException(422, "entity type must be customer or corporate")
