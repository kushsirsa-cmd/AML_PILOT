"""AI Case Summary Agent: analyst-ready case notes."""
import json

from .. import llm
from ..models import Customer, utcnow

RECOMMENDATIONS = {
    "REJECT_PROHIBITED": "REJECT / EXIT - relationship is prohibited; escalate to MLRO and sanctions officer.",
    "ESCALATE_SENIOR_APPROVAL": "ESCALATE - complete EDD and obtain senior management approval before any onboarding decision.",
    "APPROVE_WITH_EDD": "APPROVE SUBJECT TO EDD - conditional on completion of enhanced due diligence measures and enhanced monitoring.",
    "REQUEST_INFORMATION": "REQUEST INFORMATION - material gaps in KYC / SoF / SoW must be remedied before approval.",
    "APPROVE_STANDARD": "APPROVE - standard CDD complete, standard monitoring.",
}


def final_recommendation(c: Customer, ctx: dict) -> str:
    rating = ctx["risk"]["risk_rating"]
    edd, kyc, sof, sow = ctx["edd"], ctx["kyc"], ctx["sof"], ctx["sow"]
    open_sanctions = any(
        h["list_type"] == "SANCTIONS" and h["disposition"] == "OPEN" and 75 <= float(h["confidence"]) < 90
        for h in ctx["screening"]["hits"]
    )
    if rating == "PROHIBITED":
        return "REJECT_PROHIBITED"
    if open_sanctions or edd["edd_recommendation"] == "SENIOR_MANAGEMENT_APPROVAL_REQUIRED":
        return "ESCALATE_SENIOR_APPROVAL"
    gaps = bool(kyc["missing_information"]) or sof["plausibility"] == "IMPLAUSIBLE" or sow["sow_assessment"] == "INSUFFICIENT"
    if rating == "HIGH":
        return "REQUEST_INFORMATION" if gaps else "APPROVE_WITH_EDD"
    if gaps and rating == "MEDIUM":
        return "REQUEST_INFORMATION"
    return "APPROVE_STANDARD" if rating == "LOW" else "APPROVE_WITH_EDD" if edd["edd_required"] else "APPROVE_STANDARD"


def _template(c: Customer, ctx: dict, rec_key: str) -> str:
    kyc, cdd, scr, edd, sof, sow, risk = (ctx[k] for k in ("kyc", "cdd", "screening", "edd", "sof", "sow", "risk"))
    income = f"EUR {c.annual_income:,.0f}" if c.annual_income is not None else "not provided"
    risks = [r for r in risk["reasoning"] if not r.startswith("Total") and not r.startswith("Override")] + [f"Override: {o}" for o in risk["overrides"]]
    hits = [h for h in scr["hits"] if h["disposition"] != "FALSE_POSITIVE"]
    lines = [
        f"CASE NOTE - {c.customer_ref} - {c.full_name}",
        f"Generated {utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "1. CUSTOMER PROFILE",
        f"- {c.full_name}, born {c.date_of_birth}, {c.nationality} national, resident in {c.country_of_residence}.",
        f"- Occupation: {c.occupation} ({c.industry}); declared annual income {income}.",
        f"- Product / channel: {c.product} / {c.channel}.",
        f"- Source of funds: {c.source_of_funds or 'not provided'}",
        f"- Source of wealth: {c.source_of_wealth or 'not provided'}",
        f"- KYC completeness: {kyc['completeness_pct']}%" + (f" (missing: {', '.join(kyc['missing_information'])})" if kyc["missing_information"] else ""),
        "",
        "2. RISKS IDENTIFIED",
        f"- Risk rating: {risk['risk_rating']} (score {risk['risk_score']}/100).",
        *[f"- {r}" for r in risks[:10]],
        *[f"- KYC note: {n}" for n in kyc["kyc_risk_notes"]],
        f"- SoF: {sof['plausibility']} | SoW: {sow['sow_assessment']}",
        f"- EDD: {'required - ' + ', '.join(t['type'] for t in edd['triggers']) if edd['edd_required'] else 'not required'}",
        "",
        "3. SCREENING RESULTS",
        f"- Overall: {scr['screening_result']} (top confidence {scr['match_confidence_score']}%).",
        *([f"- {i}" for i in scr["risk_indicators"]] or ["- No active screening hits."]),
        *([f"- Dispositioned: {len([h for h in scr['hits'] if h['disposition'] == 'FALSE_POSITIVE'])} false positive(s)."] if any(h["disposition"] == "FALSE_POSITIVE" for h in scr["hits"]) else []),
        "",
        "4. FINAL RECOMMENDATION",
        f"- {RECOMMENDATIONS[rec_key]}",
    ]
    if kyc["missing_information"] or sow["missing_evidence"]:
        lines.append("- Outstanding items: " + "; ".join((kyc["missing_information"] + sow["missing_evidence"])[:6]))
    if edd["edd_measures"]:
        lines.append("- Priority EDD measures: " + "; ".join(edd["edd_measures"][:3]))
    lines.append("- This is an AI-assisted recommendation; the final decision rests with the human analyst.")
    del hits
    return "\n".join(lines)


def run(db, c: Customer, ctx: dict) -> dict:
    rec_key = final_recommendation(c, ctx)
    note = _template(c, ctx, rec_key)
    engine = "rules"

    facts = {k: ctx[k] for k in ("kyc", "cdd", "screening", "edd", "sof", "sow", "risk")}
    facts["screening"] = {k: v for k, v in facts["screening"].items() if k not in ("sanctions", "pep", "adverse_media")}
    ai = llm.ask(
        "Write an analyst-ready AML case note with EXACTLY these four numbered sections: "
        "1. CUSTOMER PROFILE, 2. RISKS IDENTIFIED, 3. SCREENING RESULTS, 4. FINAL RECOMMENDATION. "
        "Use short bullet lines starting with '- '. The final recommendation MUST be: "
        f"\"{RECOMMENDATIONS[rec_key]}\" - you may add a one-sentence rationale. Do not invent facts.\n\n"
        f"<customer_data>name={c.full_name}; ref={c.customer_ref}; dob={c.date_of_birth}; nationality={c.nationality}; "
        f"residence={c.country_of_residence}; occupation={c.occupation}; industry={c.industry}; income={c.annual_income}; "
        f"SoF={c.source_of_funds}; SoW={c.source_of_wealth}</customer_data>\n"
        f"<facts>{json.dumps(facts, default=str)[:14000]}</facts>",
        max_tokens=1200,
    )
    if ai and "FINAL RECOMMENDATION" in ai.upper():
        note, engine = ai, "rules+claude"

    return {
        "final_recommendation": rec_key,
        "final_recommendation_text": RECOMMENDATIONS[rec_key],
        "risk_rating": ctx["risk"]["risk_rating"],
        "case_note": note,
        "engine": engine,
    }
