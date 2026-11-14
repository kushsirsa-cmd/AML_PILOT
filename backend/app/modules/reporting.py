"""Regulatory reporting: periodic MI and statutory-style reports generated from live data, with approval and submission control."""
import csv
import io
from collections import Counter
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Alert, Analysis, AuditLog, Corporate, Customer, RegulatoryReport, Review, Sar, ScreeningHit, TravelRuleTransfer,
                      Wallet)

REPORT_TYPES = {
    "SAR_STATISTICS": "Suspicious activity reporting statistics (SARs by status, typology, time to file)",
    "CUSTOMER_RISK_MI": "Customer risk & KYC management information (ratings, EDD, PEPs, reviews, exits)",
    "CRYPTO_ACTIVITY": "Crypto-asset activity & blockchain exposure report",
    "TRAVEL_RULE": "Travel Rule compliance report (transfers, failures, counterparties)",
    "KYB_UBO": "Corporate customers: KYB ratings and beneficial-ownership transparency",
    "SANCTIONS_SCREENING": "Sanctions / PEP / adverse-media screening outcomes",
}


def _in(ts: datetime | None, start: date, end: date) -> bool:
    if ts is None:
        return False
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return datetime.combine(start, time.min, timezone.utc) <= ts <= datetime.combine(end, time.max, timezone.utc)


def _sar(db, s, e):
    sars = [x for x in db.scalars(select(Sar)) if _in(x.created_at, s, e)]
    ttf = [(x.filed_at - x.created_at).total_seconds() / 86400 for x in sars if x.filed_at]
    return dict(
        metrics=dict(total_created=len(sars), by_status=dict(Counter(x.status for x in sars)), filed=sum(x.status == "FILED" for x in sars),
                     rejected=sum(x.status == "REJECTED" for x in sars), total_value_eur=round(sum(x.total_amount_eur for x in sars), 2),
                     avg_days_to_file=round(sum(ttf) / len(ttf), 2) if ttf else None,
                     by_typology=dict(Counter(t for x in sars for t in x.typologies))),
        rows=[dict(reference=x.reference, subject=x.subject_name, subject_type=x.subject_type, status=x.status, typologies="|".join(x.typologies),
                   total_amount_eur=x.total_amount_eur, prepared_by=x.prepared_by, approved_by=x.approved_by or "", filing_reference=x.filing_reference or "",
                   created_at=x.created_at.date().isoformat(), filed_at=x.filed_at.date().isoformat() if x.filed_at else "") for x in sars])


def _risk(db, s, e):
    cs = list(db.scalars(select(Customer)))
    today = date.today()
    exits = [a for a in db.scalars(select(AuditLog).where(AuditLog.action.in_(["CASE_DECISION", "REVIEW_DECISION"]))) if _in(a.ts, s, e)
             and (a.details.get("decision") in ("REJECT", "EXIT_RELATIONSHIP"))]
    reviews = [r for r in db.scalars(select(Review)) if _in(r.created_at, s, e)]
    return dict(
        metrics=dict(total_customers=len(cs), by_rating=dict(Counter(c.risk_rating or "UNRATED" for c in cs)), by_status=dict(Counter(c.status for c in cs)),
                     pep_customers=len({c.id for c in cs if c.pep_declared} | {h.customer_id for h in db.scalars(select(ScreeningHit)) if h.list_type == "PEP" and h.confidence >= 75 and h.disposition != "FALSE_POSITIVE"}),
                     overdue_periodic_reviews=sum(1 for c in cs if c.next_review_due and c.next_review_due < today and c.status in ("ACTIVE", "UNDER_REVIEW")),
                     reviews_in_period=dict(Counter(r.review_type for r in reviews)), relationships_rejected_or_exited=len(exits)),
        rows=[dict(customer_ref=c.customer_ref, name=c.full_name, nationality=c.nationality, residence=c.country_of_residence, rating=c.risk_rating or "",
                   score=c.risk_score if c.risk_score is not None else "", status=c.status, pep_declared=c.pep_declared,
                   next_review_due=c.next_review_due.isoformat() if c.next_review_due else "") for c in cs])


def _crypto(db, s, e):
    ws = list(db.scalars(select(Wallet)))
    latest = {}
    for a in db.scalars(select(Analysis).where(Analysis.kind == "wallet_screening").order_by(Analysis.id)):
        latest[a.entity_id] = a.output
    exp = Counter()
    for o in latest.values():
        for k, v in o["exposure"]["sources_total_pct"].items():
            exp[k] += v * o["exposure"]["total_received_eur"] / 100
    return dict(
        metrics=dict(wallets_monitored=len(ws), screened=len(latest), by_risk_level=dict(Counter(w.risk_level or "UNSCREENED" for w in ws)),
                     received_eur=round(sum(o["exposure"]["total_received_eur"] for o in latest.values()), 2),
                     sent_eur=round(sum(o["exposure"]["total_sent_eur"] for o in latest.values()), 2),
                     inbound_exposure_eur_by_category={k: round(v, 2) for k, v in exp.most_common()},
                     patterns_detected=dict(Counter(p["pattern"] for o in latest.values() for p in o["patterns"]))),
        rows=[dict(wallet=w.address, chain=w.chain, owner_customer_id=w.customer_id or "", owner_corporate_id=w.corporate_id or "",
                   risk_level=w.risk_level or "", risk_score=w.risk_score if w.risk_score is not None else "") for w in ws])


def _travel(db, s, e):
    ts = [t for t in db.scalars(select(TravelRuleTransfer)) if _in(t.created_at, s, e)]
    failed = Counter(c["check"] for t in ts for c in t.checks if c["result"] == "FAIL")
    return dict(
        metrics=dict(total_transfers=len(ts), total_value_eur=round(sum(t.amount_eur for t in ts), 2), by_status=dict(Counter(t.status for t in ts)),
                     by_direction=dict(Counter(t.direction for t in ts)), self_hosted=sum(t.self_hosted for t in ts),
                     failed_checks=dict(failed), by_counterparty_vasp=dict(Counter(t.counterparty_vasp or "self-hosted" for t in ts))),
        rows=[dict(id=t.id, direction=t.direction, amount_eur=t.amount_eur, asset=t.asset, counterparty_vasp=t.counterparty_vasp or "self-hosted",
                   status=t.status, reasons=" | ".join(t.reasons), tx_hash=t.tx_hash or "") for t in ts])


def _kyb(db, s, e):
    cs = list(db.scalars(select(Corporate)))
    latest = {}
    for a in db.scalars(select(Analysis).where(Analysis.kind == "kyb").order_by(Analysis.id)):
        latest[a.entity_id] = a.output
    return dict(
        metrics=dict(corporates=len(cs), by_rating=dict(Counter(c.risk_rating or "UNRATED" for c in cs)),
                     ubo_status=dict(Counter(o["ubo_status"] for o in latest.values())),
                     opaque_structures=sum(1 for o in latest.values() if o["structure"]["risk"] == "HIGH"),
                     avg_verified_ownership_pct=round(sum(o["ubo_verified_ownership_pct"] for o in latest.values()) / len(latest), 1) if latest else None),
        rows=[dict(corp_ref=c.corp_ref, legal_name=c.legal_name, country=c.country_of_incorporation, rating=c.risk_rating or "",
                   ubo_status=latest.get(c.id, {}).get("ubo_status", ""), structure_risk=latest.get(c.id, {}).get("structure", {}).get("risk", ""),
                   recommendation=latest.get(c.id, {}).get("recommendation", "")) for c in cs])


def _screening(db, s, e):
    hs = [h for h in db.scalars(select(ScreeningHit)) if _in(h.created_at, s, e)]
    return dict(
        metrics=dict(total_hits=len(hs), by_list=dict(Counter(h.list_type for h in hs)), by_disposition=dict(Counter(h.disposition for h in hs)),
                     confirmed_sanctions=sum(1 for h in hs if h.list_type == "SANCTIONS" and h.disposition == "CONFIRMED"),
                     open_over_75=sum(1 for h in hs if h.disposition == "OPEN" and h.confidence >= 75)),
        rows=[dict(customer_id=h.customer_id, list_type=h.list_type, matched_name=h.matched_name, confidence=h.confidence, disposition=h.disposition,
                   note=h.disposition_note or "") for h in hs])


GENERATORS = {"SAR_STATISTICS": _sar, "CUSTOMER_RISK_MI": _risk, "CRYPTO_ACTIVITY": _crypto, "TRAVEL_RULE": _travel, "KYB_UBO": _kyb,
              "SANCTIONS_SCREENING": _screening}


def generate(db: Session, report_type: str, start: date, end: date, actor: str) -> RegulatoryReport:
    if report_type not in GENERATORS:
        raise ValueError(f"Unknown report type. Valid: {sorted(GENERATORS)}")
    if end < start:
        raise ValueError("period_end must be on or after period_start")
    body = GENERATORS[report_type](db, start, end)
    open_alerts = db.scalars(select(Alert).where(Alert.status != "CLOSED")).all()
    r = RegulatoryReport(report_type=report_type, title=REPORT_TYPES[report_type].split(" (")[0], period_start=start, period_end=end,
                         payload=dict(metrics=body["metrics"], rows=body["rows"], open_alerts_at_generation=len(open_alerts),
                                      generated_at=datetime.now(timezone.utc).isoformat(), disclaimer="Simulated data - illustrative format, not an official regulatory template."),
                         generated_by=actor)
    db.add(r)
    db.flush()
    return r


def to_csv(r: RegulatoryReport) -> str:
    rows = r.payload.get("rows", [])
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return buf.getvalue()


def report_dict(r: RegulatoryReport, full: bool = False) -> dict:
    d = dict(id=r.id, report_type=r.report_type, title=r.title, period_start=r.period_start.isoformat(), period_end=r.period_end.isoformat(),
             status=r.status, generated_by=r.generated_by, approved_by=r.approved_by, submission_reference=r.submission_reference,
             created_at=r.created_at.isoformat(), approved_at=r.approved_at.isoformat() if r.approved_at else None,
             submitted_at=r.submitted_at.isoformat() if r.submitted_at else None, row_count=len(r.payload.get("rows", [])),
             metrics=r.payload.get("metrics"))
    if full:
        d["rows"] = r.payload.get("rows", [])
        d["disclaimer"] = r.payload.get("disclaimer")
    return d
