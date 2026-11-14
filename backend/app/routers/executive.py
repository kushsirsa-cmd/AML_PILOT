from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, demo_data
from ..auth import CAN
from ..db import get_db
from ..deps import current_user, require_role
from ..models import Alert, Assessment, AuditLog, Corporate, Customer, QaReview, Review, Sar, Transaction
from ..modules import txmon
from ..modules.alerts import OPEN_STATUSES

router = APIRouter(prefix="/api", tags=["executive"])


def aw(t):
    return None if t is None else (t if t.tzinfo else t.replace(tzinfo=timezone.utc))


def month_key(t) -> str:
    return aw(t).strftime("%Y-%m")


def last_months(n: int) -> list[str]:
    d = date.today().replace(day=1)
    out = []
    for i in range(n - 1, -1, -1):
        m = d.month - i
        y = d.year + (m - 1) // 12
        out.append(f"{y}-{(m - 1) % 12 + 1:02d}")
    return out


@router.get("/executive")
def executive(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    customers = list(db.scalars(select(Customer)))
    corps = list(db.scalars(select(Corporate)))
    alerts = list(db.scalars(select(Alert)))
    reviews = list(db.scalars(select(Review)))
    sars = list(db.scalars(select(Sar)))
    txs = list(db.scalars(select(Transaction)))
    open_alerts = [a for a in alerts if a.status in OPEN_STATUSES]
    months = last_months(6)

    def vol(items, attr="created_at"):
        c = Counter(month_key(getattr(x, attr)) for x in items if getattr(x, attr))
        return [c.get(m, 0) for m in months]

    pending_reviews = [r for r in reviews if r.status in ("PENDING", "ESCALATED")]
    overdue = [c for c in customers if c.status == "ACTIVE" and c.next_review_due and c.next_review_due < date.today()]
    age_buckets = {"0-3 days": 0, "4-7 days": 0, "8-14 days": 0, "15-30 days": 0, "30+ days": 0}
    for a in open_alerts:
        d = (now - aw(a.created_at)).days
        age_buckets["0-3 days" if d <= 3 else "4-7 days" if d <= 7 else "8-14 days" if d <= 14 else "15-30 days" if d <= 30 else "30+ days"] += 1
    src = defaultdict(lambda: {"open": 0, "closed": 0})
    for a in alerts:
        src[a.source]["closed" if a.status == "CLOSED" else "open"] += 1
    workload = Counter(a.assigned_to or "Unassigned" for a in open_alerts)
    filed = [s for s in sars if s.status == "FILED"]
    filed_days = [(aw(s.decided_at) - aw(s.created_at)).days for s in filed if s.decided_at]
    weeks = [(date.today() - timedelta(days=7 * i)) for i in range(11, -1, -1)]
    wk_total, wk_flag = [0.0] * 12, [0.0] * 12
    wk_n, wk_fn = [0] * 12, [0] * 12
    for t in txs:
        age_w = (now - aw(t.ts)).days // 7
        if 0 <= age_w < 12:
            wk_total[11 - age_w] += t.amount_eur
            wk_n[11 - age_w] += 1
            if t.flags:
                wk_flag[11 - age_w] += t.amount_eur
                wk_fn[11 - age_w] += 1
    geo = Counter(c.country_of_residence for c in customers if c.risk_rating in ("HIGH", "PROHIBITED"))
    qa_rows = list(db.scalars(select(QaReview)))
    qa_done = [q for q in qa_rows if q.status == "COMPLETED"]
    recent = db.scalars(select(AuditLog).where(AuditLog.actor_type.in_(["USER", "SYSTEM"]), AuditLog.action != "LOGIN").order_by(AuditLog.id.desc()).limit(10)).all()
    ratings = ["LOW", "MEDIUM", "HIGH", "PROHIBITED"]
    return dict(
        generated_at=now.isoformat(),
        kpis=dict(
            total_customers=len(customers), total_businesses=len(corps),
            high_risk_customers=sum(c.risk_rating in ("HIGH", "PROHIBITED") for c in customers),
            high_risk_businesses=sum(c.risk_rating in ("HIGH", "PROHIBITED") for c in corps),
            open_alerts=len(open_alerts), critical_alerts=sum(a.severity == "CRITICAL" for a in open_alerts),
            pending_reviews=len(pending_reviews), overdue_periodic_reviews=len(overdue),
            case_volume_30d=sum(1 for x in [*alerts, *reviews, *sars] if (now - aw(x.created_at)).days <= 30),
            sars_filed=len(filed), sars_in_progress=sum(s.status in ("DRAFT", "PENDING_MLRO", "APPROVED") for s in sars),
            escalated_to_mlro=sum(a.status == "ESCALATED_MLRO" for a in alerts),
            transactions=len(txs), flagged_transactions=sum(bool(t.flags) for t in txs),
        ),
        risk_distribution=dict(customers=[sum(c.risk_rating == r for c in customers) for r in ratings], businesses=[sum(c.risk_rating == r for c in corps) for r in ratings], labels=ratings),
        customer_status=dict(Counter(c.status for c in customers)),
        case_volume=dict(months=months, alerts=vol(alerts), reviews=vol(reviews), sars=vol(sars)),
        alerts_by_source=[dict(source=k, **v) for k, v in sorted(src.items(), key=lambda kv: -(kv[1]["open"] + kv[1]["closed"]))],
        alert_ageing=age_buckets, alerts_by_severity=dict(Counter(a.severity for a in open_alerts)),
        workload=[dict(assignee=k, open_alerts=v) for k, v in workload.most_common()],
        sars=dict(by_status=dict(Counter(s.status for s in sars)), total=len(sars), filed_by_month=vol(filed, "decided_at"), created_by_month=vol(sars),
                  avg_days_to_file=round(sum(filed_days) / len(filed_days), 1) if filed_days else None, total_value_eur=round(sum(s.total_amount_eur for s in filed), 0)),
        transactions=dict(weeks=[w.strftime("%d %b") for w in weeks], total_eur=[round(x) for x in wk_total], flagged_eur=[round(x) for x in wk_flag], total_count=wk_n, flagged_count=wk_fn,
                          flags_by_rule=dict(Counter(f for t in txs for f in t.flags))),
        top_risk_countries=[dict(country=k, customers=v) for k, v in geo.most_common(6)],
        qa=dict(sampled=len(qa_rows), completed=len(qa_done), pass_rate_pct=round(100 * sum(q.outcome == "PASS" for q in qa_done) / len(qa_done), 1) if qa_done else None),
        recent_activity=[dict(ts=aw(r.ts).isoformat(), actor=r.actor, action=r.action, entity_type=r.entity_type, entity_id=r.entity_id, customer_id=r.customer_id) for r in recent],
    )


@router.get("/workqueue")
def workqueue(limit: int = Query(30, le=200), db: Session = Depends(get_db)):
    """One list per AML workflow, derived from the latest agent outputs, open alerts, reviews and SARs."""
    now = datetime.now(timezone.utc)
    customers = {c.id: c for c in db.scalars(select(Customer))}
    corps = {c.id: c for c in db.scalars(select(Corporate))}
    latest: dict[tuple[int, str], dict] = {}
    for a in db.scalars(select(Assessment).order_by(Assessment.id)):
        latest[(a.customer_id, a.agent)] = a.output

    def item(c: Customer, detail: str, age=None, assignee=None, link=None):
        return dict(entity_type="customer", entity_id=c.id, name=c.full_name, ref=c.customer_ref, rating=c.risk_rating, status=c.status, detail=detail, age_days=age, assignee=assignee,
                    link=link or f"/customers/{c.id}")

    queues: dict[str, dict] = {}

    def q(key, label, desc):
        queues[key] = dict(key=key, label=label, description=desc, items=[])
        return queues[key]["items"]

    open_c = [c for c in customers.values() if c.status in ("ONBOARDING", "UNDER_REVIEW")]
    kyc, cdd, edd, sof, sow = (q("KYC_REVIEW", "KYC review", "Onboarding profiles with incomplete information or KYC risk notes"),
                                q("CDD_REVIEW", "CDD review", "Onboarding customers needing standard / medium-risk due diligence sign-off"),
                                q("EDD_REVIEW", "EDD review", "Customers for whom enhanced due diligence is required and not yet decided"),
                                q("SOF_VERIFICATION", "SoF verification", "Source-of-funds explanation not fully plausible or lacking evidence"),
                                q("SOW_VERIFICATION", "SoW verification", "Source-of-wealth partial or insufficient"))
    for c in sorted(open_c, key=lambda x: -(x.risk_score or 0)):
        o = lambda a: latest.get((c.id, a), {})
        age = (now - aw(c.created_at)).days
        if o("kyc").get("completeness_pct", 100) < 100 or (o("kyc").get("kyc_risk_notes") and c.status == "ONBOARDING"):
            kyc.append(item(c, f"KYC {o('kyc').get('completeness_pct', '?')}% complete; missing: {', '.join(o('kyc').get('missing_information', [])[:3]) or 'see notes'}", age))
        if c.status == "ONBOARDING" and o("cdd").get("cdd_level") in ("MEDIUM", "HIGH"):
            cdd.append(item(c, f"CDD level {o('cdd').get('cdd_level')} ({o('cdd').get('cdd_score')}/{o('cdd').get('cdd_max_score')})", age))
        if o("edd").get("edd_required"):
            edd.append(item(c, "; ".join(str(t.get("detail", t)) if isinstance(t, dict) else str(t) for t in o("edd").get("triggers", [])[:2]) or "EDD required", age))
        if o("sof").get("plausibility") in ("IMPLAUSIBLE", "PARTIALLY_PLAUSIBLE"):
            sof.append(item(c, f"SoF {o('sof').get('plausibility').replace('_', ' ').lower()} (score {o('sof').get('plausibility_score')})", age))
        if o("sow").get("sow_assessment") in ("PARTIAL", "INSUFFICIENT"):
            sow.append(item(c, f"SoW {o('sow').get('sow_assessment').lower()} (score {o('sow').get('sow_score')})", age))
    by_src = {"SANCTIONS": q("SANCTIONS_ALERTS", "Sanctions alerts", "Open sanctions-list matches awaiting disposition"),
              "PEP": q("PEP_ALERTS", "PEP alerts", "Open politically-exposed-person matches"),
              "ADVERSE_MEDIA": q("SCREENING_ALERTS", "Screening alerts", "Adverse-media screening hits"),
              "TXN_MONITORING": q("TXN_ALERTS", "Transaction monitoring", "Rule-based transaction monitoring alerts"),
              "KYB": q("KYB_ALERTS", "KYB / UBO alerts", "High-risk corporate reviews and UBO gaps"),
              "CRYPTO": q("CRYPTO_ALERTS", "Crypto / Travel Rule", "Wallet-risk and Travel Rule alerts")}
    by_src["TRAVEL_RULE"] = queues["CRYPTO_ALERTS"]["items"]
    sev = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    for a in sorted(db.scalars(select(Alert).where(Alert.status.in_(["OPEN", "IN_REVIEW"]))), key=lambda x: (sev.get(x.severity, 4), x.id)):
        if a.source not in by_src:
            continue
        ent = customers.get(a.entity_id) if a.entity_type == "customer" else corps.get(a.entity_id)
        name = getattr(ent, "full_name", None) or getattr(ent, "legal_name", None) or f"{a.entity_type} {a.entity_id}"
        link = f"/customers/{a.entity_id}" if a.entity_type == "customer" else f"/kyb/{a.entity_id}" if a.entity_type == "corporate" else "/mlro"
        by_src[a.source].append(dict(entity_type=a.entity_type, entity_id=a.entity_id, name=name, ref=f"ALERT-{a.id}", rating=a.severity, status=a.status, detail=a.title,
                                     age_days=(now - aw(a.created_at)).days, assignee=a.assigned_to, link=link, alert_id=a.id))
    per, ev = q("PERIODIC_REVIEWS", "Periodic reviews", "Scheduled KYC refreshes in progress or overdue"), q("EVENT_REVIEWS", "Event-driven reviews", "Reviews triggered by address, occupation, sanctions or media events")
    for r in db.scalars(select(Review).where(Review.status.in_(["PENDING", "ESCALATED"])).order_by(Review.id.desc())):
        c = customers[r.customer_id]
        (per if r.review_type == "PERIODIC" else ev).append(item(c, f"{r.trigger.replace('_', ' ')} → {r.recommendation or 'pending'}", (now - aw(r.created_at)).days, None, f"/customers/{c.id}"))
    for c in customers.values():
        if c.status == "ACTIVE" and c.next_review_due and c.next_review_due < date.today() and not any(i["entity_id"] == c.id for i in per):
            per.append(item(c, f"Periodic review overdue since {c.next_review_due.isoformat()}", (date.today() - c.next_review_due).days))
    sar = q("SAR_ESCALATION", "SAR escalation", "Alerts escalated to the MLRO and SARs awaiting action")
    for a in db.scalars(select(Alert).where(Alert.status == "ESCALATED_MLRO").order_by(Alert.id.desc())):
        c = customers.get(a.customer_id) if a.customer_id else None
        sar.append(dict(entity_type="alert", entity_id=a.id, name=getattr(c, "full_name", a.title), ref=f"ALERT-{a.id}", rating=a.severity, status="ESCALATED_MLRO", detail=a.title,
                        age_days=(now - aw(a.created_at)).days, assignee=a.assigned_to, link="/mlro"))
    for s in db.scalars(select(Sar).where(Sar.status.in_(["DRAFT", "PENDING_MLRO", "APPROVED"])).order_by(Sar.id.desc())):
        sar.append(dict(entity_type="sar", entity_id=s.id, name=s.subject_name, ref=s.reference, rating=None, status=s.status, detail=f"{', '.join(s.typologies[:2])} · EUR {s.total_amount_eur:,.0f}",
                        age_days=(now - aw(s.created_at)).days, assignee=s.prepared_by, link=f"/sars/{s.id}"))
    for qd in queues.values():
        qd["count"] = len(qd["items"])
        qd["items"] = qd["items"][:limit]
    return dict(queues=list(queues.values()))


# ---------------------------------------------------------------- transactions
@router.get("/transactions/fiat")
def fiat_transactions(flagged: bool = False, customer_id: int | None = None, corporate_id: int | None = None, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(Transaction).order_by(Transaction.ts.desc())
    if customer_id:
        stmt = stmt.where(Transaction.customer_id == customer_id)
    if corporate_id:
        stmt = stmt.where(Transaction.corporate_id == corporate_id)
    names = {c.id: c.full_name for c in db.scalars(select(Customer))}
    knames = {c.id: c.legal_name for c in db.scalars(select(Corporate))}
    out = []
    for t in db.scalars(stmt):
        if flagged and not t.flags:
            continue
        out.append(dict(txn_ref=t.txn_ref, ts=aw(t.ts).isoformat(), direction=t.direction, amount_eur=t.amount_eur, channel=t.channel, counterparty=t.counterparty,
                        counterparty_country=t.counterparty_country, flags=t.flags, customer_id=t.customer_id, corporate_id=t.corporate_id,
                        holder=names.get(t.customer_id) or knames.get(t.corporate_id), holder_type="customer" if t.customer_id else "corporate"))
        if len(out) >= limit:
            break
    return dict(rules={k: dict(severity=v[0], description=v[1]) for k, v in txmon.RULES.items()}, transactions=out)


@router.post("/transactions/monitor")
def rerun_monitoring(db: Session = Depends(get_db), user: str = Depends(current_user)):
    r = txmon.monitor(db)
    audit.log(db, actor=user, actor_type=audit.USER, action="TXN_MONITORING_RUN", entity_type="system", details=r)
    db.commit()
    return r


# ---------------------------------------------------------------- admin
@router.get("/admin/system")
def system_info(db: Session = Depends(get_db), _: str = Depends(require_role(*CAN["admin"]))):
    from sqlalchemy import func

    from ..config import settings

    return dict(llm_active=settings.llm_active, model=settings.claude_model, seed_size=settings.seed_size, demo_open_access=settings.demo_open_access,
                counts=dict(customers=db.scalar(select(func.count(Customer.id))), corporates=db.scalar(select(func.count(Corporate.id))), transactions=db.scalar(select(func.count(Transaction.id))),
                            alerts=db.scalar(select(func.count(Alert.id))), sars=db.scalar(select(func.count(Sar.id))), audit_rows=db.scalar(select(func.count(AuditLog.id)))))


@router.post("/admin/demo/reset")
def reset_demo(db: Session = Depends(get_db), _: str = Depends(require_role(*CAN["admin"]))):
    """Wipe all data and rebuild the deterministic demo dataset (takes a few seconds)."""
    return demo_data.reset_and_seed(db)
