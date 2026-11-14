"""EDD Agent: decides whether enhanced due diligence is required and which measures apply."""
from ..models import Customer
from .base import customer_facts, narrate
from .screening import effective_confidence

MEASURES = {
    "HIGH_RISK_COUNTRY": [
        "Obtain and verify evidence of the customer's ties to the high-risk jurisdiction and reason for the relationship.",
        "Corroborate source of funds with documentary evidence (bank statements, contracts, tax filings).",
        "Apply enhanced ongoing transaction monitoring with lower alert thresholds.",
    ],
    "PEP": [
        "Obtain senior management approval before establishing / continuing the relationship.",
        "Establish source of wealth AND source of funds with independent corroboration.",
        "Identify close family members and associates (RCAs); apply annual enhanced review.",
    ],
    "HIGH_RISK_INDUSTRY": [
        "Obtain business licences / registrations and evidence of regulatory supervision where applicable.",
        "Understand business model, key counterparties and expected transaction flows.",
        "Apply sector-specific red-flag monitoring scenarios.",
    ],
    "SANCTIONS_POTENTIAL_MATCH": [
        "Escalate to the sanctions team for adjudication before any account activity is permitted.",
        "Obtain additional identifiers (passport number, place of birth) to confirm or discount the match.",
    ],
    "ADVERSE_MEDIA": [
        "Review the underlying articles for reliability and relevance; document the outcome.",
        "Ask the customer to explain the allegations and obtain supporting evidence.",
    ],
}


def run(db, c: Customer, ctx: dict) -> dict:
    cdd, scr = ctx["cdd"], ctx["screening"]
    triggers: list[dict] = []

    if cdd["geography"]["level"] in ("HIGH", "PROHIBITED"):
        triggers.append({"type": "HIGH_RISK_COUNTRY", "detail": cdd["geography"]["reason"]})
    if cdd["industry"]["level"] == "HIGH":
        triggers.append({"type": "HIGH_RISK_INDUSTRY", "detail": cdd["industry"]["reason"]})

    active = [h for h in scr["hits"] if h["disposition"] != "FALSE_POSITIVE"]
    peps = [h for h in active if h["list_type"] == "PEP" and effective_confidence(h) >= 75]
    if c.pep_declared or peps:
        who = "self-declared" if c.pep_declared else ""
        if peps:
            who = (who + "; " if who else "") + "; ".join(f"{h['matched_name']} ({h['details']['record'].get('position')})" for h in peps)
        triggers.append({"type": "PEP", "detail": f"PEP status: {who}."})
    sanc = [h for h in active if h["list_type"] == "SANCTIONS" and 75 <= effective_confidence(h) < 90]
    if sanc:
        triggers.append({"type": "SANCTIONS_POTENTIAL_MATCH", "detail": "Potential sanctions match(es): " + ", ".join(h["matched_name"] for h in sanc)})
    media = [h for h in active if h["list_type"] == "ADVERSE_MEDIA" and effective_confidence(h) >= 75]
    if media:
        triggers.append({"type": "ADVERSE_MEDIA", "detail": "Adverse media: " + "; ".join(h["details"]["record"].get("headline", h["matched_name"]) for h in media)})

    confirmed_sanction = any(h["list_type"] == "SANCTIONS" and effective_confidence(h) >= 90 for h in active)
    prohibited = cdd["geography"]["prohibited_residence"] or confirmed_sanction

    if prohibited:
        recommendation = "DECLINE_OR_EXIT"
    elif any(t["type"] == "PEP" for t in triggers):
        recommendation = "SENIOR_MANAGEMENT_APPROVAL_REQUIRED"
    elif triggers:
        recommendation = "PROCEED_WITH_EDD_MEASURES"
    else:
        recommendation = "EDD_NOT_REQUIRED"

    measures: list[str] = []
    for t in triggers:
        for m in MEASURES.get(t["type"], []):
            if m not in measures:
                measures.append(m)
    if prohibited:
        measures = ["Do not onboard / freeze existing relationship; escalate to the MLRO and sanctions officer immediately."] + measures

    fallback = (
        ("EDD is required. " if triggers else "EDD is not required. ")
        + (f"Triggers: {', '.join(t['type'].replace('_', ' ').lower() for t in triggers)}. " if triggers else "No high-risk country, PEP, high-risk industry or screening triggers were identified. ")
        + f"Recommendation: {recommendation.replace('_', ' ').lower()}."
    )
    summary, engine = narrate(
        "Write an EDD summary for the analyst explaining why EDD is or is not required and what the priority measures are.",
        {"customer": customer_facts(c), "triggers": triggers, "recommendation": recommendation, "measures": measures},
        fallback,
    )
    return {
        "edd_required": bool(triggers) or prohibited,
        "triggers": triggers,
        "edd_summary": summary,
        "edd_recommendation": recommendation,
        "edd_measures": measures,
        "engine": engine,
    }
