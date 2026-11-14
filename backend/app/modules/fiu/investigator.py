"""AML INVESTIGATIONS AGENT - prepares the full investigation workbook for an alert (nine-step workflow), detailed case notes
and a disposition recommendation. The agent prepares and recommends; people complete each step and own every decision."""
from __future__ import annotations

from datetime import date

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Alert, Analysis, Assessment, Corporate, Customer, Document, Review, ScreeningHit, Sar, Transaction, TravelRuleTransfer, Wallet
from .common import aware, entity_txs, etype_of, key, load_entity, money, name_of, now, profile_amount, ref_of

STEPS = [
    (1, "ALERT_CREATED", "Alert created"), (2, "TRIAGE", "Triage review"), (3, "EVIDENCE", "Evidence collection"), (4, "CUSTOMER_REVIEW", "Customer review"),
    (5, "TXN_ANALYSIS", "Transaction analysis"), (6, "RISK_ASSESSMENT", "Risk assessment"), (7, "ESCALATION", "Escalation decision"), (8, "SAR_CONSIDERATION", "SAR consideration"),
    (9, "CLOSURE", "Closure decision"),
]
DISPOSITIONS = {
    "FALSE_POSITIVE": "Alert is a false positive (identity / rule trigger not supported by facts)",
    "NO_SUSPICION": "Investigated - activity explained, no suspicion",
    "ENHANCED_MONITORING": "No suspicion yet - place the relationship under enhanced monitoring",
    "SUSPICION_NO_SAR": "Some concern but threshold for reporting not met - rationale recorded",
    "SAR_FILED": "Suspicion confirmed - report approved and filed by the MLRO",
    "EXIT_RELATIONSHIP": "Relationship to be exited / declined (risk outside appetite)",
}


def subject_of_alert(db: Session, a: Alert) -> tuple[str, int] | None:
    if a.entity_type in ("customer", "corporate"):
        return a.entity_type, a.entity_id
    if a.entity_type == "wallet":
        w = db.get(Wallet, a.entity_id)
        if w and w.customer_id:
            return "customer", w.customer_id
        if w and w.corporate_id:
            return "corporate", w.corporate_id
    if a.customer_id:
        return "customer", a.customer_id
    return None


def _triage(db: Session, a: Alert | None, etype: str, eid: int, obj, det: dict) -> dict:
    """Type-specific triage: is this alert worth a full investigation?"""
    if a is None:
        return dict(alert_type="MANUAL", outcome="PROCEED", verdict="Case opened from risk-based review", factors=["Opened proactively - no source alert to triage"], priority_hint="HIGH" if det["risk_score"] >= 60 else "MEDIUM")
    f, verdict, outcome = [], "UNRESOLVED", "PROCEED"
    t = a.source
    if t in ("SANCTIONS", "PEP", "ADVERSE_MEDIA") and etype == "customer":
        h = db.get((ScreeningHit), (a.details or {}).get("hit_id")) if (a.details or {}).get("hit_id") else None
        rec = (h.details or {}).get("record", {}) if h else {}
        sim = fuzz.token_sort_ratio(obj.full_name.lower(), (h.matched_name if h else "").lower()) if h else 0
        f.append(f"Name similarity {sim:.0f}% (screening confidence {h.confidence:.0f}%)" if h else "No screening record linked")
        if rec.get("dob"):
            same = rec["dob"] == obj.date_of_birth.isoformat()
            f.append(f"Date of birth {'matches' if same else 'DIFFERS'} ({rec['dob']} vs {obj.date_of_birth.isoformat()})")
            verdict = "LIKELY_TRUE_MATCH" if same and sim >= 90 else "LIKELY_FALSE_POSITIVE" if not same else "UNRESOLVED"
        if rec.get("nationality"):
            f.append(f"Nationality {'matches' if rec['nationality'] == obj.nationality else 'differs'} ({rec['nationality']} vs {obj.nationality})")
            if rec["nationality"] != obj.nationality and verdict != "LIKELY_FALSE_POSITIVE":
                verdict = "LIKELY_FALSE_POSITIVE" if verdict == "UNRESOLVED" else verdict
        if t == "SANCTIONS" and rec:
            f.append(f"{rec.get('list')} / {rec.get('program')}: {rec.get('reason')}")
        if t == "PEP" and rec:
            f.append(f"{rec.get('position')} ({rec.get('category')}); PEP declared by customer: {'yes' if obj.pep_declared else 'NO - undeclared'}")
            verdict = verdict if verdict != "UNRESOLVED" else "UNRESOLVED"
        if t == "ADVERSE_MEDIA" and rec:
            f.append(f"{rec.get('severity')} {rec.get('category')}: {rec.get('headline')} ({rec.get('source')}, {rec.get('date')})")
        if verdict == "LIKELY_FALSE_POSITIVE":
            outcome = "CLOSE_FALSE_POSITIVE"
    elif t == "TXN_MONITORING":
        d = a.details or {}
        f.append(f"Rule {str(d.get('rule', '')).replace('_', ' ').lower()} - {len(d.get('txn_refs', []))} transaction(s), {money(d.get('total_eur', 0))}")
        prior = db.scalars(select(Alert).where(Alert.entity_type == a.entity_type, Alert.entity_id == a.entity_id, Alert.id != a.id)).all()
        f.append(f"{len(prior)} other alert(s) on this entity" if prior else "First alert on this entity")
        verdict = "CORROBORATED_BY_TYPOLOGY" if det["detections"] else "NO_TYPOLOGY_CORROBORATION"
        if not det["detections"] and not prior and (d.get("total_eur") or 0) < 20000:
            outcome, verdict = "CLOSE_FALSE_POSITIVE", "LIKELY_FALSE_POSITIVE"
            f.append("No typology corroboration and no alert history: probably a rule trigger without suspicious context")
    elif t == "CRYPTO":
        d = a.details or {}
        f.append(f"Wallet score {d.get('score')}; patterns: {', '.join(d.get('patterns', [])) or 'none'}")
        verdict = "CORROBORATED_BY_TYPOLOGY" if any(x["code"] == "CRYPTO_LAUNDERING" for x in det["detections"]) else "UNRESOLVED"
    elif t == "TRAVEL_RULE":
        f.append("Travel Rule exception on a crypto transfer - check originator / beneficiary information and VASP counterparty")
    elif t == "KYB":
        f.append(f"UBO status {(a.details or {}).get('ubo_status')}; recommendation {(a.details or {}).get('recommendation')}")
    else:
        f.append(a.description[:200])
    return dict(alert_type=t, outcome=outcome, verdict=verdict, factors=f, priority_hint=a.severity)


def _evidence(db: Session, etype: str, eid: int, obj, a: Alert | None, txs, det: dict) -> dict:
    items = []

    def add(item, status, detail):
        items.append(dict(item=item, status=status, detail=detail))

    if etype == "customer":
        docs = list(db.scalars(select(Document).where(Document.customer_id == eid)))
        kinds = {d.doc_type for d in docs}
        add("Identity document", "COLLECTED" if "ID_DOCUMENT" in kinds else "MISSING", ", ".join(sorted(kinds)) or "no documents on file")
        add("Proof of address", "COLLECTED" if "PROOF_OF_ADDRESS" in kinds else "MISSING", "")
        add("Source of funds evidence", "COLLECTED" if kinds & {"PAYSLIP", "BANK_STATEMENT", "SOF_EVIDENCE"} else "MISSING", "")
        add("Source of wealth evidence", "COLLECTED" if kinds & {"TAX_RETURN", "SOW_EVIDENCE", "INHERITANCE"} else "MISSING", "")
        hits = db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == eid)).all()
        add("Screening record", "COLLECTED" if hits else "NOT_APPLICABLE", f"{len(hits)} hit(s), {sum(1 for h in hits if h.disposition == 'OPEN')} open")
    else:
        k = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == eid, Analysis.kind == "kyb").order_by(Analysis.id.desc()).limit(1))
        add("KYB review", "COLLECTED" if k else "MISSING", f"UBO status {k.output['ubo_status']}" if k else "")
        add("Ownership chart", "COLLECTED" if k else "MISSING", "")
    add("Transaction extract", "COLLECTED" if txs else "MISSING", f"{len(txs)} transaction(s)")
    wallets = list(db.scalars(select(Wallet).where((Wallet.customer_id == eid) if etype == "customer" else (Wallet.corporate_id == eid))))
    add("Wallet screening", "COLLECTED" if wallets else "NOT_APPLICABLE", f"{len(wallets)} wallet(s)")
    add("Network / link analysis", "COLLECTED", "Entity Link Analysis agent run")
    add("Prior alerts and decisions", "COLLECTED", "see timeline")
    add("Customer explanation", "MISSING", "Not yet requested. Ask via the relationship manager - never reveal the investigation (tipping-off).")
    have = sum(1 for i in items if i["status"] == "COLLECTED")
    need = sum(1 for i in items if i["status"] != "NOT_APPLICABLE")
    return dict(items=items, completeness_pct=round(100 * have / need) if need else 100)


def _customer_review(db: Session, etype: str, eid: int, obj) -> dict:
    f = []
    out = dict(rating=getattr(obj, "risk_rating", None), score=getattr(obj, "risk_score", None), status=obj.status)
    if etype == "customer":
        ass = {a.agent: a.output for a in db.scalars(select(Assessment).where(Assessment.customer_id == eid).order_by(Assessment.id))}
        out.update(kyc_completeness=ass.get("kyc", {}).get("completeness_pct"), cdd_level=ass.get("cdd", {}).get("cdd_level"), edd_required=ass.get("edd", {}).get("edd_required"),
                   sof=ass.get("sof", {}).get("plausibility"), sow=ass.get("sow", {}).get("sow_assessment"), pep_declared=obj.pep_declared,
                   onboarded=obj.onboarded_at.isoformat() if obj.onboarded_at else None, last_kyc_review=obj.last_kyc_review.isoformat() if obj.last_kyc_review else None,
                   next_review_due=obj.next_review_due.isoformat() if obj.next_review_due else None, occupation=obj.occupation, declared_income=obj.annual_income)
        if out["kyc_completeness"] is not None and out["kyc_completeness"] < 100:
            f.append(f"KYC {out['kyc_completeness']}% complete")
        if out["edd_required"]:
            f.append("EDD required")
        if out["sof"] in ("IMPLAUSIBLE", "PARTIALLY_PLAUSIBLE"):
            f.append(f"Source of funds {out['sof'].lower().replace('_', ' ')}")
        if out["sow"] in ("PARTIAL", "INSUFFICIENT"):
            f.append(f"Source of wealth {out['sow'].lower()}")
        if obj.next_review_due and obj.next_review_due < date.today():
            f.append("Periodic review overdue")
        reviews = db.scalars(select(Review).where(Review.customer_id == eid)).all()
        out["reviews"] = [dict(type=r.review_type, status=r.status, decision=r.decision) for r in reviews[-4:]]
    else:
        k = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == eid, Analysis.kind == "kyb").order_by(Analysis.id.desc()).limit(1))
        if k:
            out.update(ubo_status=k.output["ubo_status"], structure_risk=k.output["structure"].get("structure_risk"), recommendation=k.output["recommendation"],
                       red_flags=[x["detail"] for x in k.output["structure"]["red_flags"]][:5])
            f += [x["detail"] for x in k.output["structure"]["red_flags"]][:3]
    out["concerns"] = f
    return out


def _txn_analysis(txs, det: dict) -> dict:
    flagged = [t for t in txs if t.flags]
    return dict(total=len(txs), flagged=len(flagged), flagged_eur=round(sum(t.amount_eur for t in flagged)), rules=sorted({f for t in flagged for f in t.flags}),
                inflow=round(sum(t.amount_eur for t in txs if t.direction == "IN")), outflow=round(sum(t.amount_eur for t in txs if t.direction == "OUT")),
                countries=sorted({t.counterparty_country for t in txs if t.counterparty_country and t.counterparty_country != "Poland"})[:10],
                typologies=[dict(code=d["code"], label=d["label"], score=d["score"], indicators=[i["text"] for i in d["indicators"][:3]], refs=d["refs"][:8]) for d in det["detections"][:4]])


def prepare(db: Session, etype: str, eid: int, alert: Alert | None, current_step: int, det: dict, rbi_report: dict, fiu_report: dict | None) -> dict:
    """Build the nine-step workbook, case notes and disposition recommendation."""
    obj = load_entity(db, etype, eid)
    txs = entity_txs(db, etype, eid)
    triage = _triage(db, alert, etype, eid, obj, det)
    evidence = _evidence(db, etype, eid, obj, alert, txs, det)
    cust = _customer_review(db, etype, eid, obj)
    ta = _txn_analysis(txs, det)
    conf = rbi_report["confidence"]["score"]
    risk = dict(typology_score=det["risk_score"], network_score=(rbi_report.get("network") or {}).get("score", 0), confidence=conf, priority=rbi_report["priority"]["level"],
                for_=[i["text"] for d in det["detections"][:3] for i in d["indicators"][:2]][:6], against=rbi_report["mitigating_facts"][:4])
    esc = rbi_report["escalation"]
    if fiu_report:
        esc = dict(recommendation=("ESCALATE_MLRO" if fiu_report["sar_recommendation"]["urgency"].startswith("PRIORITY") else esc["recommendation"]), rationale=esc["rationale"], human_decision_required=True)
    role_needed = {"ESCALATE_MLRO": "MLRO", "ESCALATE_FIU": "Senior Analyst", "ENHANCED_MONITORING": "Analyst", "GATHER_EVIDENCE": "Analyst", "NO_ACTION": "Analyst"}.get(esc["recommendation"], "Senior Analyst")
    sarrec = fiu_report["sar_recommendation"] if fiu_report else dict(recommendation="DO_NOT_FILE", rationale="FIU analysis not run", urgency="STANDARD", human_decision_required=True)
    if triage["outcome"] == "CLOSE_FALSE_POSITIVE":
        disp, why = "FALSE_POSITIVE", "Triage indicates a false positive: " + "; ".join(triage["factors"][:2])
    elif sarrec["recommendation"] == "FILE":
        disp, why = "SAR_FILED", "FIU assessment supports filing; subject to MLRO decision."
    elif esc["recommendation"] == "ENHANCED_MONITORING":
        disp, why = "ENHANCED_MONITORING", esc["rationale"]
    elif det["risk_score"] < 25:
        disp, why = "NO_SUSPICION", "No typology reached threshold; mitigating facts present."
    else:
        disp, why = "SUSPICION_NO_SAR", "Concern remains but evidence is insufficient for a report - gather more information first."
    step_defs = {
        1: dict(summary=(f"Alert #{alert.id} {alert.source} / {alert.severity}: {alert.title}" if alert else "Case opened proactively (no source alert)"), findings=[alert.description[:240]] if alert else ["Opened by risk-based review / FIU"], data=dict(alert_id=alert.id if alert else None)),
        2: dict(summary=f"Triage verdict: {triage['verdict'].replace('_', ' ').lower()} - recommended outcome {triage['outcome'].replace('_', ' ').lower()}", findings=triage["factors"], data=triage),
        3: dict(summary=f"Evidence {evidence['completeness_pct']}% complete", findings=[f"{i['item']}: {i['status'].lower()}" + (f" ({i['detail']})" if i['detail'] else "") for i in evidence["items"]], data=evidence),
        4: dict(summary=f"{cust['rating'] or 'unrated'} customer; {len(cust['concerns'])} concern(s)", findings=cust["concerns"] or ["No KYC / CDD concerns identified"], data=cust),
        5: dict(summary=f"{ta['total']} transactions, {ta['flagged']} flagged ({money(ta['flagged_eur'])}); {len(ta['typologies'])} typology match(es)",
                findings=[f"{t['label']} (score {t['score']}): {t['indicators'][0]}" for t in ta["typologies"] if t["indicators"]] or ["No typology matched"], data=ta),
        6: dict(summary=f"Typology risk {risk['typology_score']}, network {risk['network_score']}, case confidence {conf}/100", findings=["For: " + x for x in risk["for_"]] + ["Against: " + x for x in risk["against"]], data=risk),
        7: dict(summary=f"Recommendation: {esc['recommendation'].replace('_', ' ').lower()} (decision by {role_needed})", findings=[esc["rationale"]], data=dict(**esc, decision_maker=role_needed)),
        8: dict(summary=f"SAR consideration: {sarrec['recommendation'].replace('_', ' ').lower()}", findings=[sarrec["rationale"], sarrec.get("tipping_off_warning", "")], data=sarrec),
        9: dict(summary=f"Proposed disposition: {disp.replace('_', ' ').lower()}", findings=[why], data=dict(recommended=disp, rationale=why, options=DISPOSITIONS)),
    }
    steps = []
    for n, k, title in STEPS:
        status = "DONE" if n < current_step else "CURRENT" if n == current_step else "PENDING"
        steps.append(dict(n=n, key=k, title=title, status=status, owner=("system" if n == 1 else "analyst"), **step_defs[n]))
    notes = [f"INVESTIGATION CASE NOTES - {name_of(obj)} ({ref_of(obj)})", f"Prepared by AML Investigations agent (rules engine), {now():%Y-%m-%d %H:%M} UTC. Draft for investigator review.", ""]
    for s in steps:
        notes.append(f"STEP {s['n']} - {s['title'].upper()}: {s['summary']}")
        notes += [f"  - {x}" for x in s["findings"][:8] if x]
        notes.append("")
    notes.append(f"RECOMMENDED DISPOSITION: {disp} - {why}")
    notes.append("All decisions (triage outcome, escalation, SAR and closure) are made by authorised staff; this workbook is decision support.")
    return dict(steps=steps, case_notes="\n".join(notes), disposition=dict(recommended=disp, rationale=why, human_decision_required=True), triage=triage,
                escalation=dict(**esc, decision_maker=role_needed), sar_consideration=sarrec)
