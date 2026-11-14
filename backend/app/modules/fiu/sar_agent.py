"""SAR / STR AGENT - drafts the report content (facts, behaviour, concerns, red flags, escalation history, evidence) and renders it in four
ILLUSTRATIVE formats. The formats are NOT schema-valid regulator submissions: real filing goes through the regulator's own portal
(UK: NCA SAR Online; Canada: FINTRAC web reporting / API; Singapore: STRO SONAR) and must be completed by the MLRO / nominated officer."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Alert, Investigation
from .common import aware, money, now

DISCLAIMER = ("ILLUSTRATIVE FORMAT - not a schema-valid submission. Re-key or map into the regulator's official channel. "
              "Prepared by an AI-assisted rules engine; must be reviewed, completed and approved by the MLRO / nominated officer.")

FORMATS = {
    "UK_SAR": dict(label="UK SAR (NCA / UKFIU)", note="A UK SAR is filed by the FCA-regulated firm with the NCA's UK Financial Intelligence Unit under POCA 2002 / Terrorism Act 2000. The FCA is the supervisor, not the recipient."),
    "FINTRAC_STR": dict(label="FINTRAC STR (Canada)", note="Filed with FINTRAC under the PCMLTFA when there are reasonable grounds to suspect; 'as soon as practicable' once those grounds are established."),
    "MAS_STR": dict(label="MAS-ready STR (STRO, Singapore)", note="Singapore STRs are filed with the Suspicious Transaction Reporting Office (STRO, Commercial Affairs Department), not with MAS itself."),
    "FIU_INTEL": dict(label="FIU intelligence package", note="Internal / disclosable intelligence package for the FIU or law-enforcement liaison."),
}


def content(fiu: dict, rbi: dict | None, inv: Investigation | None, db: Session) -> dict:
    """Jurisdiction-neutral report content."""
    det, susp, subj = fiu["typology"], fiu["suspicion"], fiu["subject"]
    pkg = fiu["intelligence_package"]
    fin = pkg["financial_summary"]
    facts = [f"Subject: {subj['name']} ({subj['ref']}), {subj['type']}, risk rating {subj.get('rating') or 'n/a'}.",
             f"Activity window {fin['first']} to {fin['last']}: {fin['transactions']} transactions, {money(fin['total_in_eur'])} in, {money(fin['total_out_eur'])} out."]
    if fiu.get("mule_network"):
        facts.append(fiu["mule_network"]["summary"])
    behaviour = [i["text"] for d in det["detections"][:4] for i in d["indicators"][:3]]
    concerns = susp["factors_for"][:6]
    red_flags = [f"{d['label']}: {d['description']}" for d in det["detections"][:5]]
    if fiu["network"]["hidden_associations"]:
        red_flags.append("Undeclared association: " + fiu["network"]["hidden_associations"][0]["explanation"])
    esc = []
    if inv:
        esc.append(f"Investigation {inv.reference} opened {aware(inv.created_at):%Y-%m-%d} (source {inv.source_type}), now in queue {inv.queue}.")
        for n in (inv.notes or [])[-6:]:
            esc.append(f"{n.get('ts', '')[:10]} {n.get('author', '')}: {n.get('text', '')[:140]}")
        if inv.alert_id:
            a = db.get(Alert, inv.alert_id)
            if a:
                esc.append(f"Originating alert #{a.id} ({a.source}, {a.severity}): {a.title}")
    evidence = [f"{t['ref']} {t['ts'][:10]} {t['direction']} {money(t['eur'])} {t.get('counterparty') or ''} ({t.get('country') or ''})" for t in pkg["key_transactions"][:10]]
    if rbi:
        facts.append(f"RBI case confidence {rbi['confidence']['score']}/100; priority {rbi['priority']['level']}.")
    unusual = not det["detections"] or not susp["factors_against"]
    return dict(subject=subj, typologies=[dict(code=d["code"], label=d["label"], score=d["score"]) for d in det["detections"]], typology_classification=det["typologies"],
                grounds_for_suspicion=("; ".join(concerns[:3]) or "Not established"), facts=facts, behaviour=behaviour, concerns=concerns, red_flags=red_flags,
                escalation_history=esc, evidence=evidence, mitigating=susp["factors_against"], total_amount_eur=round(fin["total_in_eur"] + fin["total_out_eur"]),
                associates=[a["name"] for a in pkg["associates"]][:10], wallets=pkg["wallets"], sar_recommendation=fiu["sar_recommendation"]["recommendation"], unexplained=unusual)


def narrative(c: dict) -> str:
    p = [f"This report concerns {c['subject']['name']} ({c['subject']['ref']})."]
    p += c["facts"]
    if c["behaviour"]:
        p.append("Observed behaviour: " + " ".join(c["behaviour"][:5]))
    if c["red_flags"]:
        p.append("Red flags: " + " | ".join(c["red_flags"][:4]) + ".")
    if c["mitigating"]:
        p.append("Considered and not outweighing: " + "; ".join(c["mitigating"][:3]) + ".")
    p.append("The activity has not been satisfactorily explained by the information held. No approach has been made to the subject about this report.")
    return "\n".join(p)


def render(fmt: str, c: dict, reference: str) -> dict:
    txt = narrative(c)
    base = dict(format=fmt, label=FORMATS[fmt]["label"], destination_note=FORMATS[fmt]["note"], disclaimer=DISCLAIMER, reference=reference, generated_at=now().isoformat())
    if fmt == "UK_SAR":
        return dict(**base, sections=[
            ("Reporter", "Regulated-sector firm (placeholder) - nominated officer: MLRO"), ("Report type", "Suspicious Activity Report; consent (DAML) requested: " + ("consider - see MLRO" if c["sar_recommendation"] == "FILE" else "no")),
            ("Subject", f"{c['subject']['name']} ({c['subject']['ref']})"), ("Reason for suspicion", c["grounds_for_suspicion"]), ("Suspected criminality / typology", ", ".join(t["label"] for t in c["typologies"]) or "To be determined"),
            ("Value involved", money(c["total_amount_eur"])), ("Narrative", txt), ("Linked parties", ", ".join(c["associates"]) or "None identified"),
            ("Supporting transactions", "\n".join(c["evidence"]) or "None"), ("Glossary codes", "Indicative only - choose from the current UKFIU glossary codes list")])
    if fmt == "FINTRAC_STR":
        return dict(**base, sections=[
            ("Part A - Reporting entity", "Placeholder"), ("Part B - Transaction(s)", "\n".join(c["evidence"]) or "None"), ("Part C - Person / entity", f"{c['subject']['name']} ({c['subject']['ref']})"),
            ("Part D - Reasonable grounds to suspect (RGS)", c["grounds_for_suspicion"]), ("Part E - Indicators", "\n".join(c["red_flags"]) or "None"), ("Part F - Narrative", txt),
            ("Part G - Action taken", "; ".join(c["escalation_history"][:3]) or "Internal investigation"), ("Timing", "Submit as soon as practicable after RGS is established - the MLRO sets the date")])
    if fmt == "MAS_STR":
        return dict(**base, sections=[
            ("Filer", "Placeholder - Compliance Officer / MLRO"), ("Subject", f"{c['subject']['name']} ({c['subject']['ref']})"), ("Grounds for suspicion", c["grounds_for_suspicion"]),
            ("Nature of suspected offence", ", ".join(t["label"] for t in c["typologies"]) or "To be determined"), ("Transactions", "\n".join(c["evidence"]) or "None"), ("Related parties", ", ".join(c["associates"]) or "None"),
            ("Narrative", txt), ("Action taken by the institution", "; ".join(c["escalation_history"][:3]) or "Under review")])
    return dict(**base, sections=[
        ("Handling", "OFFICIAL-SENSITIVE (simulated) - intelligence use only"), ("Subject", f"{c['subject']['name']} ({c['subject']['ref']})"), ("Assessment", f"{', '.join(t['label'] for t in c['typologies']) or 'No typology'}"),
        ("Network", ", ".join(c["associates"]) or "None"), ("Wallets", ", ".join(w["address"] for w in c["wallets"]) or "None"), ("Narrative", txt), ("Evidence", "\n".join(c["evidence"]) or "None")])


def build(fiu: dict, rbi: dict | None, inv: Investigation | None, db: Session, reference: str | None = None) -> dict:
    c = content(fiu, rbi, inv, db)
    ref = reference or f"DRAFT-{fiu['subject']['ref']}"
    return dict(content=c, narrative=narrative(c), formats={k: render(k, c, ref) for k in FORMATS}, disclaimer=DISCLAIMER,
                human_decision_required=True, tipping_off_warning="Do not tip off the subject. Only the MLRO may approve and file.")
