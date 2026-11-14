"""Suspicious Activity Report generator: evidence collection, typology mapping, narrative drafting, goAML-style XML."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, llm
from ..models import Alert, Analysis, Assessment, AddressLabel, AuditLog, ChainTx, Corporate, Customer, Sar, ScreeningHit, TravelRuleTransfer, Wallet

TYPOLOGIES = {
    "SANCTIONS_EVASION": "Possible sanctions evasion / dealings with designated persons",
    "STRUCTURING": "Structuring of transfers below reporting thresholds",
    "LAYERING": "Layering through rapid pass-through or peel-chain movement of funds",
    "MIXER_OBFUSCATION": "Use of mixing services to obscure the origin of funds",
    "ILLICIT_MARKET_PROCEEDS": "Funds linked to darknet markets, ransomware or scams",
    "PEP_CORRUPTION_RISK": "PEP exposure with corruption indicators",
    "ADVERSE_MEDIA_CRIME": "Adverse media linking the subject to predicate offences",
    "SHELL_COMPANY_OPACITY": "Opaque corporate structure (nominees, secrecy jurisdictions, circular ownership)",
    "TRAVEL_RULE_EVASION": "Transfers lacking or evading required originator / beneficiary information",
    "UNEXPLAINED_WEALTH": "Source of funds / wealth implausible or unsubstantiated",
}


def _wallet_evidence(db: Session, wallets: list[Wallet], ev: dict) -> None:
    for w in wallets:
        a = db.scalar(select(Analysis).where(Analysis.entity_type == "wallet", Analysis.entity_id == w.id).order_by(Analysis.id.desc()).limit(1))
        if not a:
            continue
        o = a.output
        if o["risk_level"] in ("HIGH", "SEVERE"):
            ev["indicators"].append(f"Wallet {w.address[:12]}... screened {o['risk_level']} (score {o['risk_score']}): " + "; ".join(o["risk_indicators"][:3]))
        for p in o["patterns"]:
            ev["tx_hashes"].update(p["tx_hashes"])
            ev["typologies"].update({"STRUCTURING": ["STRUCTURING"], "PEEL_CHAIN": ["LAYERING"], "RAPID_PASS_THROUGH": ["LAYERING"]}.get(p["pattern"], []))
        src = o["exposure"]["sources_total_pct"]
        if src.get("MIXER", 0) >= 5 or any(t["category"] == "MIXER" for t in o["risky_traces"]):
            ev["typologies"].add("MIXER_OBFUSCATION")
        if any(src.get(c, 0) >= 3 for c in ("DARKNET", "RANSOMWARE", "SCAM")) or any(t["category"] in ("DARKNET", "RANSOMWARE", "SCAM") for t in o["risky_traces"]):
            ev["typologies"].add("ILLICIT_MARKET_PROCEEDS")
        if any(src.get(c, 0) > 0 for c in ("SANCTIONED", "TERRORISM_FINANCING")):
            ev["typologies"].add("SANCTIONS_EVASION")
        for t in o["risky_traces"]:
            for step in t["path"]:
                ev["tx_hashes"].add(step["tx_hash"])


def build_evidence(db: Session, subject_type: str, subject_id: int) -> dict:
    ev: dict = dict(indicators=[], typologies=set(), tx_hashes=set(), actions=[], customer_id=None)
    wallets: list[Wallet] = []
    if subject_type == "customer":
        c = db.get(Customer, subject_id)
        if not c:
            raise LookupError("Customer not found")
        ev["customer_id"] = c.id
        ev["subject"] = dict(type="customer", id=c.id, ref=c.customer_ref, name=c.full_name, dob=c.date_of_birth.isoformat(), nationality=c.nationality,
                             country=c.country_of_residence, occupation=c.occupation, rating=c.risk_rating, score=c.risk_score)
        wallets = list(db.scalars(select(Wallet).where(Wallet.customer_id == c.id)))
        for h in db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == c.id)):
            if h.disposition == "FALSE_POSITIVE" or h.confidence < 75:
                continue
            rec = h.details.get("record", {})
            ev["indicators"].append(f"{h.list_type.replace('_', ' ').title()} match ({h.confidence:.0f}%, {h.disposition.lower()}): {h.matched_name} - "
                                    f"{rec.get('reason') or rec.get('position') or rec.get('headline') or ''}")
            if h.list_type == "SANCTIONS" and (h.confidence >= 90 or h.disposition == "CONFIRMED"):
                ev["typologies"].add("SANCTIONS_EVASION")
            if h.list_type == "PEP":
                ev["typologies"].add("PEP_CORRUPTION_RISK")
            if h.list_type == "ADVERSE_MEDIA":
                ev["typologies"].add("ADVERSE_MEDIA_CRIME")
        risk = db.scalar(select(Assessment).where(Assessment.customer_id == c.id, Assessment.agent == "risk").order_by(Assessment.id.desc()).limit(1))
        if risk:
            ev["indicators"] += [f"Risk engine: {r}" for r in risk.output["reasoning"][:4] if not r.startswith("Total")]
            if risk.output["components"].get("source_of_funds", {}).get("points", 0) >= 15:
                ev["typologies"].add("UNEXPLAINED_WEALTH")
        ev["actions"].append(f"Customer risk-rated {c.risk_rating} (score {c.risk_score}); relationship status {c.status}.")
    elif subject_type == "corporate":
        corp = db.get(Corporate, subject_id)
        if not corp:
            raise LookupError("Corporate not found")
        ev["subject"] = dict(type="corporate", id=corp.id, ref=corp.corp_ref, name=corp.legal_name, country=corp.country_of_incorporation,
                             registration_number=corp.registration_number, industry=corp.industry, rating=corp.risk_rating, score=corp.risk_score)
        wallets = list(db.scalars(select(Wallet).where(Wallet.corporate_id == corp.id)))
        k = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == corp.id).order_by(Analysis.id.desc()).limit(1))
        if k:
            o = k.output
            ev["indicators"].append(f"KYB rating {o['risk_rating']} ({o['risk_score']}); UBO status {o['ubo_status']}.")
            ev["indicators"] += [f"Structure: {f['detail']}" for f in o["structure"]["red_flags"]]
            ev["indicators"] += [f"Screening: {h['party']} ~ {h['matched_name']} ({h['list_type']}, {h['confidence']:.0f}%)" for h in o["screening_hits"]]
            codes = {f["code"] for f in o["structure"]["red_flags"]}
            if codes & {"NOMINEES", "CIRCULAR_OWNERSHIP", "SECRECY_JURISDICTION", "NO_UBO_IDENTIFIED"}:
                ev["typologies"].add("SHELL_COMPANY_OPACITY")
            if any(h["list_type"] == "SANCTIONS" and h["confidence"] >= 90 for h in o["screening_hits"]):
                ev["typologies"].add("SANCTIONS_EVASION")
        ev["actions"].append(f"Corporate risk-rated {corp.risk_rating}; status {corp.status}.")
    elif subject_type == "wallet":
        w = db.get(Wallet, subject_id)
        if not w:
            raise LookupError("Wallet not found")
        if w.customer_id:
            return build_evidence(db, "customer", w.customer_id)
        if w.corporate_id:
            return build_evidence(db, "corporate", w.corporate_id)
        wallets = [w]
        ev["subject"] = dict(type="wallet", id=w.id, ref=w.address, name=w.address, chain=w.chain, rating=w.risk_level, score=w.risk_score)
    else:
        raise ValueError("subject_type must be customer, corporate or wallet")

    _wallet_evidence(db, wallets, ev)
    wallet_ids = [w.id for w in wallets]
    cust_filter = [TravelRuleTransfer.customer_id == ev["customer_id"]] if ev["customer_id"] else []
    trs = list(db.scalars(select(TravelRuleTransfer).where(
        TravelRuleTransfer.status.in_(["REJECT", "HOLD_REQUEST_INFO"]),
        (TravelRuleTransfer.wallet_id.in_(wallet_ids) if wallet_ids else TravelRuleTransfer.id < 0)
        | (cust_filter[0] if cust_filter else TravelRuleTransfer.id < 0))))
    for t in trs:
        ev["indicators"].append(f"Travel Rule {t.status}: {t.direction} EUR {t.amount_eur:,.0f} - " + "; ".join(t.reasons[:2]))
        ev["typologies"].add("TRAVEL_RULE_EVASION")
        if t.tx_hash:
            ev["tx_hashes"].add(t.tx_hash)
    for al in db.scalars(select(Alert).where(Alert.entity_type == ev["subject"]["type"], Alert.entity_id == ev["subject"]["id"])):
        ev["actions"].append(f"Alert #{al.id} '{al.title}' raised ({al.severity}), status {al.status}.")
    if ev["customer_id"]:
        for row in db.scalars(select(AuditLog).where(AuditLog.customer_id == ev["customer_id"], AuditLog.action.in_(
                ["CASE_DECISION", "REVIEW_DECISION", "SCREENING_HIT_DISPOSITION"])).order_by(AuditLog.id)):
            ev["actions"].append(f"{row.ts:%Y-%m-%d} {row.action} by {row.actor}: {row.details.get('decision') or row.details.get('to')}.")

    txs = list(db.scalars(select(ChainTx).where(ChainTx.tx_hash.in_(list(ev["tx_hashes"]))).order_by(ChainTx.ts))) if ev["tx_hashes"] else []
    labels = {}
    for l in db.scalars(select(AddressLabel)):
        labels[l.address] = l.entity_name
    ev["transactions"] = [dict(tx_hash=t.tx_hash, ts=t.ts.isoformat(), from_address=t.from_address, to_address=t.to_address,
                               from_entity=labels.get(t.from_address), to_entity=labels.get(t.to_address), asset=t.asset, amount_eur=t.amount_eur) for t in txs]
    ev["total_amount_eur"] = round(sum(t.amount_eur for t in txs), 2)
    ev["period"] = dict(**{"from": txs[0].ts.date().isoformat(), "to": txs[-1].ts.date().isoformat()}) if txs else None
    ev["typologies"] = sorted(ev["typologies"])
    ev.pop("tx_hashes")
    return ev


def draft_narrative(ev: dict, reference: str) -> tuple[str, str]:
    s = ev["subject"]
    lines = [
        f"SUSPICIOUS ACTIVITY REPORT - {reference} (DRAFT)", "",
        "1. SUBJECT",
        f"- {s['name']} ({s['type']}, ref {s['ref']})" + (f", {s.get('nationality', '')} national, resident in {s.get('country', '')}" if s["type"] == "customer" else f", incorporated in {s.get('country', '')}" if s["type"] == "corporate" else "") + ".",
        f"- Current risk rating: {s.get('rating')} (score {s.get('score')}).", "",
        "2. SUMMARY OF SUSPICION",
        "- " + ("; ".join(TYPOLOGIES[t] for t in ev["typologies"]) if ev["typologies"] else "Multiple risk indicators warrant review (no specific typology mapped)."), "",
        "3. ACTIVITY DESCRIPTION (who / what / when / where / how)",
    ]
    if ev["transactions"]:
        p = ev["period"]
        lines.append(f"- {len(ev['transactions'])} transaction(s) totalling EUR {ev['total_amount_eur']:,.2f} between {p['from']} and {p['to']} were identified as relevant.")
        for t in ev["transactions"][:6]:
            lines.append(f"  - {t['ts'][:10]} EUR {t['amount_eur']:,.0f} {t['asset']} {t['from_entity'] or t['from_address'][:10] + '...'} -> {t['to_entity'] or t['to_address'][:10] + '...'} ({t['tx_hash'][:14]}...)")
    else:
        lines.append("- No specific transactions were isolated; suspicion is based on customer-level indicators below.")
    lines += ["", "4. GROUNDS FOR SUSPICION / INDICATORS"] + [f"- {i}" for i in ev["indicators"][:12]]
    lines += ["", "5. ACTIONS TAKEN BY THE INSTITUTION"] + [f"- {a}" for a in ev["actions"][:8]]
    lines += ["", "6. RECOMMENDATION",
              "- File with the FIU; apply enhanced monitoring and restrict activity pending MLRO decision.",
              "- Do not inform the subject of this report (tipping-off prohibition)."]
    text = "\n".join(lines)
    ai = llm.ask(
        "Rewrite this draft SAR narrative into clear, factual FIU-ready prose. Keep EXACTLY the six numbered section headings "
        "(1. SUBJECT, 2. SUMMARY OF SUSPICION, 3. ACTIVITY DESCRIPTION, 4. GROUNDS FOR SUSPICION / INDICATORS, 5. ACTIONS TAKEN BY THE INSTITUTION, 6. RECOMMENDATION). "
        "Do not add facts, amounts or names that are not in the draft.\n\n<facts>" + text + "</facts>", max_tokens=1500)
    if ai and "GROUNDS FOR SUSPICION" in ai.upper() and "RECOMMENDATION" in ai.upper():
        return ai, "rules+claude"
    return text, "rules"


def generate(db: Session, subject_type: str, subject_id: int, *, actor: str, alert_id: int | None = None) -> Sar:
    ev = build_evidence(db, subject_type, subject_id)
    sar = Sar(reference="PENDING", subject_type=ev["subject"]["type"], subject_id=ev["subject"]["id"], subject_name=ev["subject"]["name"],
              customer_id=ev["customer_id"], alert_id=alert_id, typologies=ev["typologies"], evidence=ev, narrative="",
              total_amount_eur=ev["total_amount_eur"], prepared_by=actor)
    db.add(sar)
    db.flush()
    sar.reference = f"SAR-{datetime.now(timezone.utc).year}-{sar.id:04d}"
    sar.narrative, sar.engine = draft_narrative(ev, sar.reference)
    audit.log(db, actor=f"SAR Generator ({sar.engine})", actor_type=audit.AI, action="SAR_DRAFTED", entity_type="sar", entity_id=sar.id,
              customer_id=sar.customer_id, details=dict(requested_by=actor, subject=sar.subject_name, typologies=sar.typologies, total_eur=sar.total_amount_eur))
    return sar


NARRATIVE_SECTIONS = ("SUBJECT", "SUMMARY OF SUSPICION", "ACTIVITY DESCRIPTION", "GROUNDS FOR SUSPICION", "ACTIONS TAKEN", "RECOMMENDATION")


def narrative_gaps(text: str) -> list[str]:
    up = text.upper()
    return [s for s in NARRATIVE_SECTIONS if s not in up]


def to_xml(sar: Sar) -> str:
    """Simplified goAML-style XML. Illustrative only - NOT schema-valid for any real FIU."""
    r = ET.Element("report")
    ET.SubElement(r, "rentity_id").text = "AML-COPILOT-SIM"
    ET.SubElement(r, "submission_code").text = "E"
    ET.SubElement(r, "report_code").text = "STR"
    ET.SubElement(r, "entity_reference").text = sar.reference
    ET.SubElement(r, "submission_date").text = (sar.filed_at or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")
    ET.SubElement(r, "currency_code_local").text = "EUR"
    ET.SubElement(r, "reason").text = sar.narrative
    ET.SubElement(r, "action").text = "Enhanced monitoring; activity restricted pending FIU feedback"
    s = sar.evidence["subject"]
    subj = ET.SubElement(r, "subject", type=s["type"])
    ET.SubElement(subj, "name").text = s["name"]
    ET.SubElement(subj, "reference").text = str(s.get("ref"))
    for k in ("dob", "nationality", "country", "registration_number"):
        if s.get(k):
            ET.SubElement(subj, k).text = str(s[k])
    ind = ET.SubElement(r, "report_indicators")
    for t in sar.typologies:
        ET.SubElement(ind, "indicator").text = t
    for t in sar.evidence.get("transactions", []):
        tr = ET.SubElement(r, "transaction")
        ET.SubElement(tr, "transactionnumber").text = t["tx_hash"]
        ET.SubElement(tr, "date_transaction").text = t["ts"]
        ET.SubElement(tr, "amount_local").text = f"{t['amount_eur']:.2f}"
        ET.SubElement(tr, "from_account").text = t["from_address"]
        ET.SubElement(tr, "to_account").text = t["to_address"]
        ET.SubElement(tr, "asset").text = t["asset"]
    ET.indent(r)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Illustrative goAML-style export; not schema-valid -->\n' + ET.tostring(r, encoding="unicode")
