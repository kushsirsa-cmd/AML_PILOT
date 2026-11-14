"""RBI AGENT (Risk Based Investigation) - customer risk story, timeline, behavioural analysis, hypotheses, confidence and escalation advice.

Rules engine with an optional Claude rewrite of the narrative only. The agent proposes; a human decides.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import llm
from ...data.risk_tables import HIGH_RISK_COUNTRIES, PROHIBITED_COUNTRIES
from ...models import Alert, Analysis, Assessment, AuditLog, Corporate, Customer, Investigation, Review, Sar, ScreeningHit, Wallet
from .common import aware, entity_txs, etype_of, key, level, load_entity, money, name_of, now, profile_amount, ref_of
from .links import LinkIndex, build_index
from .typology import TYPOLOGIES, detect

TESTS = {
    "STRUCTURING": ["Obtain the full deposit history (branch / ATM / time of day)", "Ask the relationship manager whether the customer has explained the deposits", "Check for linked accounts depositing at the same branches"],
    "SMURFING": ["Identify the common beneficiary account and its holder", "Review who instructed / funded each small deposit (CCTV / device data where lawful)", "Check linked accounts for the same pattern"],
    "LAYERING": ["Trace each outbound payment to the final beneficiary", "Request the commercial rationale for the pass-through", "Check whether the counterparties are linked to each other"],
    "MULE_ACCOUNT": ["Contact the customer through the normal relationship channel (no tipping-off) to understand the source of credits", "Check account opening circumstances and any recent change of device / phone", "Look for victim reports or scam alerts on inbound payers"],
    "TBML": ["Request invoices, contracts, bills of lading and customs declarations", "Compare invoiced value with market price and shipping route", "Verify the counterparties exist and trade in the goods concerned"],
    "TERRORIST_FINANCING": ["Escalate to the MLRO immediately - do not contact the customer", "Verify the recipients / collectives against the NPO registers and designations lists", "Consider whether a terrorism-specific report is required"],
    "HUMAN_TRAFFICKING": ["Escalate to the MLRO - consider law-enforcement liaison", "Review account control indicators (third-party access, shared devices) and customer welfare cues", "Do not tip off; follow victim-safe handling guidance"],
    "SANCTIONS_EVASION": ["Escalate to the sanctions team and MLRO now", "Confirm or discount each designation match against secondary identifiers", "Consider freezing / blocking obligations before any customer contact"],
    "ROUND_TRIPPING": ["Request the underlying contracts / invoices for both legs", "Check whether the two parties are under common control", "Compare the service value with market rates"],
    "CRYPTO_LAUNDERING": ["Run the Crypto Investigation agent (trace, cluster, bridge, exposure)", "Confirm attribution with at least two blockchain-analytics providers", "Request wallet ownership proof and exchange statements"],
}


def _timeline(db: Session, etype: str, eid: int, obj, txs, det: dict) -> list[dict]:
    ev: list[dict] = []

    def add(ts, kind, title, detail="", sev="INFO"):
        if ts:
            ev.append(dict(ts=aware(ts).isoformat(), kind=kind, title=title, detail=detail, severity=sev))

    if etype == "customer":
        if obj.onboarded_at:
            add(__import__("datetime").datetime.combine(obj.onboarded_at, __import__("datetime").time()), "ONBOARDING", "Customer onboarded", f"Risk rating at onboarding not recorded; product {obj.product}")
        for r in db.scalars(select(Review).where(Review.customer_id == eid)):
            add(r.completed_at or r.created_at, "REVIEW", f"{r.review_type.replace('_', ' ').title()} review {r.status.lower()}", f"Trigger: {r.trigger}" + (f"; decision {r.decision}" if r.decision else ""), "INFO")
        for h in db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == eid)):
            add(h.created_at, "SCREENING", f"{h.list_type.replace('_', ' ').title()} hit ({h.confidence:.0f}%): {h.matched_name}", f"Disposition: {h.disposition}", "HIGH" if h.confidence >= 90 else "MEDIUM")
        for a in db.scalars(select(AuditLog).where(AuditLog.customer_id == eid, AuditLog.action.in_(["CASE_DECISION", "REVIEW_DECISION", "SAR_DRAFTED"])).order_by(AuditLog.id)):
            add(a.ts, "DECISION", a.action.replace("_", " ").title(), f"by {a.actor}", "INFO")
        wallets = list(db.scalars(select(Wallet).where(Wallet.customer_id == eid)))
    else:
        wallets = list(db.scalars(select(Wallet).where(Wallet.corporate_id == eid)))
        add(obj.created_at, "ONBOARDING", "Corporate record created", f"{obj.entity_type.replace('_', ' ').title()} in {obj.country_of_incorporation}")
    for a in db.scalars(select(Alert).where(((Alert.entity_type == etype) & (Alert.entity_id == eid)) | (Alert.customer_id == eid if etype == "customer" else Alert.id < 0))):
        add(a.created_at, "ALERT", f"Alert raised: {a.title}", a.description[:160], a.severity)
        if a.escalated_at:
            add(a.escalated_at, "ESCALATION", f"Alert #{a.id} escalated to MLRO", a.resolution or "", "HIGH")
        if a.closed_at:
            add(a.closed_at, "ALERT_CLOSED", f"Alert #{a.id} closed", (a.resolution or "")[:140], "INFO")
    for s in db.scalars(select(Sar).where((Sar.customer_id == eid) if etype == "customer" else (Sar.subject_type == "corporate") & (Sar.subject_id == eid))):
        add(s.created_at, "SAR", f"{s.reference} {s.status.lower().replace('_', ' ')}", ", ".join(s.typologies[:3]), "HIGH")
    for w in wallets:
        add(w.last_screened_at, "CRYPTO", f"Wallet {w.address[:10]}... screened {w.risk_level}", f"score {w.risk_score}", "HIGH" if w.risk_level in ("HIGH", "SEVERE") else "INFO")
    by_rule: dict[str, list] = defaultdict(list)
    for t in txs:
        for f in t.flags:
            by_rule[f].append(t)
    for rule, items in by_rule.items():
        add(items[0].ts, "TXN_FLAG", f"Monitoring rule {rule.replace('_', ' ').lower()} first fired", f"{len(items)} transaction(s), {money(sum(x.amount_eur for x in items))}", "MEDIUM")
    for t in sorted(txs, key=lambda x: -x.amount_eur)[:3]:
        if t.amount_eur >= 20000:
            add(t.ts, "TXN", f"Large {t.direction.lower()}bound {t.channel.lower()} {money(t.amount_eur)}", f"{t.counterparty} ({t.counterparty_country})", "MEDIUM")
    for inv in db.scalars(select(Investigation).where(Investigation.entity_type == etype, Investigation.entity_id == eid)):
        add(inv.created_at, "INVESTIGATION", f"Investigation {inv.reference} opened", inv.title, "INFO")
    return sorted(ev, key=lambda e: e["ts"])[-60:]


def _behaviour(obj, txs) -> dict:
    nowt = now()
    real = [t for t in txs if t.channel != "CARD"]
    inflow = sum(t.amount_eur for t in real if t.direction == "IN" and (nowt - aware(t.ts)).days <= 90)
    outflow = sum(t.amount_eur for t in real if t.direction == "OUT" and (nowt - aware(t.ts)).days <= 90)
    profile = profile_amount(obj)
    last30 = [t for t in real if (nowt - aware(t.ts)).days <= 30]
    prev60 = [t for t in real if 30 < (nowt - aware(t.ts)).days <= 90]
    v30 = sum(t.amount_eur for t in last30) / 30
    v60 = sum(t.amount_eur for t in prev60) / 60 if prev60 else 0
    chan = Counter()
    for t in txs:
        chan[t.channel] += t.amount_eur
    tot = sum(chan.values()) or 1
    cps = Counter()
    for t in txs:
        cps[(t.counterparty, t.counterparty_country)] += t.amount_eur
    hr = sum(t.amount_eur for t in txs if t.counterparty_country.lower() in HIGH_RISK_COUNTRIES | PROHIBITED_COUNTRIES)
    months: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for t in real:
        m = aware(t.ts).strftime("%Y-%m")
        months[m][0 if t.direction == "IN" else 1] += t.amount_eur
    series = [dict(month=m, inflow=round(v[0]), outflow=round(v[1])) for m, v in sorted(months.items())[-6:]]
    return dict(inflow_90d=round(inflow), outflow_90d=round(outflow), declared_annual_profile=profile,
                inflow_vs_quarterly_profile=round(inflow / (profile / 4), 2) if profile else None, tx_count=len(txs),
                channel_mix={k: round(100 * v / tot) for k, v in chan.most_common()}, cash_share_pct=round(100 * chan.get("CASH", 0) / tot),
                high_risk_geography_pct=round(100 * hr / tot), distinct_counterparties=len({c for c, _ in cps}),
                top_counterparties=[dict(name=n, country=c, eur=round(v)) for (n, c), v in cps.most_common(5)],
                velocity_ratio_30d_vs_prior=round(v30 / v60, 1) if v60 else None, monthly=series,
                largest=max(((t.amount_eur, t.txn_ref) for t in txs), default=(0, None))[0])


def _risk_factors(db: Session, etype: str, eid: int) -> list[dict]:
    comps = {}
    if etype == "customer":
        a = db.scalar(select(Assessment).where(Assessment.customer_id == eid, Assessment.agent == "risk").order_by(Assessment.id.desc()).limit(1))
        comps = a.output["components"] if a else {}
    else:
        a = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == eid, Analysis.kind == "kyb").order_by(Analysis.id.desc()).limit(1))
        comps = a.output["components"] if a else {}
    return sorted([dict(factor=k, points=v["points"], reason=v["reason"]) for k, v in comps.items() if v.get("points", 0) > 0], key=lambda f: -f["points"])


def _correlations(obj, etype, factors, beh, det, wallets_risky: bool, net: dict | None) -> list[dict]:
    fs = {f["factor"] for f in factors}
    codes = {d["code"]: d["score"] for d in det["detections"]}
    out = []

    def add(a, b, strength, text):
        out.append(dict(factor=a, behaviour=b, strength=strength, explanation=text))

    if fs & {"geography", "nationality", "incorporation_jurisdiction", "operating_jurisdictions"} and beh["high_risk_geography_pct"] >= 15:
        add("High-risk geography in profile", f"{beh['high_risk_geography_pct']}% of value moves to / from high-risk jurisdictions", min(95, 50 + beh["high_risk_geography_pct"]), "Profile risk and actual money flows point at the same jurisdictions - corroborating.")
    if "pep" in fs and beh["inflow_vs_quarterly_profile"] and beh["inflow_vs_quarterly_profile"] > 1.5:
        add("PEP / RCA status", f"Inflows are {beh['inflow_vs_quarterly_profile']}x the declared quarterly profile", 80, "A PEP receiving more than declared income suggests unexplained wealth.")
    if "adverse_media" in fs and codes:
        add("Adverse media", ", ".join(TYPOLOGIES[c][0] for c in codes), 75, "Adverse media about predicate offences coincides with transactional typology indicators.")
    if fs & {"source_of_funds", "source_of_wealth"} and beh["inflow_vs_quarterly_profile"] and beh["inflow_vs_quarterly_profile"] > 1.5:
        add("Weak source of funds / wealth", f"Inflows {beh['inflow_vs_quarterly_profile']}x declared profile", 70, "Activity exceeds what the documented sources can explain.")
    if wallets_risky and beh["channel_mix"].get("CRYPTO_OFFRAMP"):
        add("High-risk wallet exposure", "Fiat credits from crypto off-ramps", 85, "On-chain risk is being converted into the banking system.")
    if net and net["score"] >= 35:
        add("Network links", f"Member of a {net['level'].lower()}-risk network", net["score"], "Behaviour is corroborated by connected accounts (shared identifiers).")
    if "kyc_quality" in fs and (beh["inflow_vs_quarterly_profile"] or 0) > 1:
        add("KYC data gaps", "High activity on an incompletely evidenced profile", 55, "Missing KYC evidence reduces the institution's ability to explain the activity.")
    return sorted(out, key=lambda c: -c["strength"])


def _mitigating(obj, etype, beh, factors, net) -> list[str]:
    m = []
    onboarded = getattr(obj, "onboarded_at", None)
    if onboarded and (now().date() - onboarded).days > 730:
        m.append(f"Long-standing relationship (onboarded {onboarded.isoformat()}) with no earlier concerns recorded")
    if beh["inflow_vs_quarterly_profile"] is not None and beh["inflow_vs_quarterly_profile"] <= 1.1:
        m.append("Activity is consistent with the declared income / turnover profile")
    if not any(f["factor"] in ("source_of_funds", "source_of_wealth") and f["points"] >= 15 for f in factors):
        m.append("Source of funds / wealth documented and assessed plausible")
    if beh["high_risk_geography_pct"] == 0:
        m.append("No payments to or from high-risk jurisdictions")
    if not net or net["score"] < 25:
        m.append("No unexplained links to other customers")
    return m


def build(db: Session, etype: str, eid: int, idx: LinkIndex | None = None, det: dict | None = None, net: dict | None = None) -> dict:
    obj = load_entity(db, etype, eid)
    idx = idx or build_index(db)
    txs = entity_txs(db, etype, eid)
    det = det or detect(db, etype, eid, idx)
    if net is None:
        from .network import analyze as net_analyze
        net_full = net_analyze(db, etype, eid)
        net = net_full["network_risk"] if net_full["linked"] else None
    beh = _behaviour(obj, txs)
    factors = _risk_factors(db, etype, eid)
    wallets = list(db.scalars(select(Wallet).where((Wallet.customer_id == eid) if etype == "customer" else (Wallet.corporate_id == eid))))
    wallets_risky = any(w.risk_level in ("HIGH", "SEVERE") for w in wallets)
    corr = _correlations(obj, etype, factors, beh, det, wallets_risky, net)
    timeline = _timeline(db, etype, eid, obj, txs, det)
    mitigating = _mitigating(obj, etype, beh, factors, net)

    # --- hypotheses (always includes the benign explanation, to counter confirmation bias)
    hyps = []
    for d in det["detections"][:4]:
        like = "HIGH" if d["score"] >= 70 else "MEDIUM" if d["score"] >= 45 else "LOW"
        hyps.append(dict(id=f"H-{d['code']}", title=f"{d['label']}", statement=d["description"], likelihood=like, score=d["score"], supporting=[i["text"] for i in d["indicators"]][:5],
                         contradicting=mitigating[:3], next_steps=TESTS.get(d["code"], []), caveat=d.get("caveat", "")))
    benign_score = max(5, 100 - det["risk_score"])
    hyps.append(dict(id="H-BENIGN", title="Legitimate explanation", statement="The activity has a legitimate commercial or personal explanation that has not yet been evidenced.",
                     likelihood="HIGH" if benign_score >= 70 else "MEDIUM" if benign_score >= 45 else "LOW", score=benign_score, supporting=mitigating[:5],
                     contradicting=[i["text"] for d in det["detections"][:2] for i in d["indicators"][:2]],
                     next_steps=["Ask the relationship manager / customer for supporting documents through the normal channel (avoid tipping-off)", "Compare against peer customers with a similar profile"], caveat=""))

    # --- case confidence
    cats = set()
    if det["detections"]:
        cats.add("transactional")
    if any(h for h in db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == eid, ScreeningHit.disposition != "FALSE_POSITIVE", ScreeningHit.confidence >= 75))) if etype == "customer" else False:
        cats.add("screening")
    if net and net["score"] >= 35:
        cats.add("network")
    if wallets_risky:
        cats.add("crypto")
    if beh["inflow_vs_quarterly_profile"] and beh["inflow_vs_quarterly_profile"] > 1.5:
        cats.add("profile mismatch")
    if any(f["factor"] == "adverse_media" for f in factors):
        cats.add("adverse media")
    strong = [d for d in det["detections"] if d["score"] >= 40]
    kyc_pct = 100
    if etype == "customer":
        k = db.scalar(select(Assessment).where(Assessment.customer_id == eid, Assessment.agent == "kyc").order_by(Assessment.id.desc()).limit(1))
        kyc_pct = k.output.get("completeness_pct", 100) if k else 60
    comp = dict(evidence_breadth=min(30, 10 * len(cats)), corroboration=min(30, 10 * len(strong)), network=round(min(15, (net["score"] if net else 0) / 100 * 15)),
                data_quality=round(15 * kyc_pct / 100), contradicting_evidence=-min(20, 4 * len(mitigating)))
    conf = max(0, min(100, sum(comp.values())))

    # --- priority
    flagged_total = sum(t.amount_eur for t in txs if t.flags)
    open_alerts = list(db.scalars(select(Alert).where(((Alert.entity_type == etype) & (Alert.entity_id == eid)), Alert.status != "CLOSED")))
    oldest = max(((now() - aware(a.created_at)).days for a in open_alerts), default=0)
    pcomp = dict(risk=round(0.5 * det["risk_score"]), exposure=round(0.2 * min(100, flagged_total / 100000 * 100)), ageing=round(0.15 * min(100, oldest / 30 * 100)),
                 network=round(0.15 * (net["score"] if net else 0)))
    pscore = sum(pcomp.values())
    priority = dict(score=pscore, level="CRITICAL" if pscore >= 65 else "HIGH" if pscore >= 45 else "MEDIUM" if pscore >= 25 else "LOW", components=pcomp, open_alerts=len(open_alerts), flagged_eur=round(flagged_total))

    top = det["detections"][0] if det["detections"] else None
    rec = det["escalation"]
    if conf < 35 and rec["recommendation"] == "ESCALATE_FIU":
        rec = dict(recommendation="GATHER_EVIDENCE", rationale="Indicators present but confidence is low - collect more evidence before escalating.", human_decision_required=True)
    # --- narrative
    paras = [f"{name_of(obj)} ({ref_of(obj)}) is rated {getattr(obj, 'risk_rating', None) or 'unrated'}" + (f" (score {obj.risk_score})" if getattr(obj, 'risk_score', None) is not None else "") + f" and has {len(open_alerts)} open alert(s).",
             ("The strongest indicator is " + f"{top['label'].lower()} (score {top['score']}): " + "; ".join(i['text'] for i in top['indicators'][:2]) + ".") if top else "No typology reached the reporting threshold; the activity is broadly in line with expectations.",
             (f"Risk factors and behaviour reinforce each other: {corr[0]['explanation']}" if corr else "Profile risk factors and observed behaviour do not clearly reinforce each other."),
             (f"The customer is connected to {net['level'].lower()}-risk network (score {net['score']}) through shared identifiers." if net else "No unexplained links to other customers were found."),
             f"Case confidence is {conf}/100. Mitigating facts: " + ("; ".join(mitigating[:3]) if mitigating else "none identified") + f". Recommendation: {rec['recommendation'].replace('_', ' ').lower()} - {rec['rationale']}"]
    narrative, engine = "\n\n".join(paras), "rules"
    ai = llm.ask("Rewrite this risk narrative for a financial-crime investigator in clear factual prose (max 220 words). Do not add facts, names or numbers that are not present.\n\n<facts>" + narrative + "</facts>", 500)
    if ai:
        narrative, engine = ai, "rules+claude"
    return dict(subject=dict(type=etype, id=eid, ref=ref_of(obj), name=name_of(obj), rating=getattr(obj, "risk_rating", None), score=getattr(obj, "risk_score", None), status=obj.status),
                timeline=timeline, risk_factors=factors, correlations=corr, behaviour=beh, patterns=[dict(code=d["code"], label=d["label"], score=d["score"]) for d in det["detections"]],
                hypotheses=hyps, mitigating_facts=mitigating, narrative=narrative, engine=engine, confidence=dict(score=conf, components=comp), priority=priority, escalation=rec,
                typology_risk_score=det["risk_score"], network=net)


def queue(db: Session, limit: int = 25) -> list[dict]:
    """RBI review queue: high-risk customers / corporates ranked by investigation priority, excluding those already under open investigation."""
    idx = build_index(db)
    busy = {(i.entity_type, i.entity_id) for i in db.scalars(select(Investigation).where(Investigation.queue != "CLOSED"))}
    rows = []
    cands = [("customer", c) for c in db.scalars(select(Customer).where(Customer.risk_rating.in_(["HIGH", "PROHIBITED"]), Customer.status != "REJECTED"))]
    cands += [("corporate", k) for k in db.scalars(select(Corporate).where(Corporate.risk_rating.in_(["HIGH", "PROHIBITED"])))]
    for et, o in cands:
        if (et, o.id) in busy:
            continue
        d = detect(db, et, o.id, idx)
        alerts = db.scalars(select(Alert).where(Alert.entity_type == et, Alert.entity_id == o.id, Alert.status != "CLOSED")).all()
        score = round(0.7 * d["risk_score"] + 0.3 * min(100, 20 * len(alerts)))
        rows.append(dict(entity_type=et, entity_id=o.id, name=name_of(o), ref=ref_of(o), rating=o.risk_rating, typology_score=d["risk_score"], typologies=d["typologies"],
                         open_alerts=len(alerts), priority_score=score, priority=level(score), recommendation=d["escalation"]["recommendation"]))
    return sorted(rows, key=lambda r: -r["priority_score"])[:limit]
