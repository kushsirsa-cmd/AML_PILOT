"""Source of Funds Agent: plausibility of the customer's explanation for the money flowing through the account."""
from .. import llm
from ..models import Customer
from .base import annualised_expected_activity, customer_facts

SPECIFIC = ("salary", "payroll", "wages", "employment", "dividend", "pension", "rental", "rent from", "sale of", "inheritance",
            "savings", "bonus", "invoice", "contract", "loan", "pension", "benefit", "profit")
RISKY = {
    "cash": "References to cash as a funding source increase placement risk.",
    "crypto": "Crypto-asset proceeds require wallet / exchange provenance evidence.",
    "bitcoin": "Crypto-asset proceeds require wallet / exchange provenance evidence.",
    "gambling": "Gambling proceeds are difficult to evidence and are a known laundering typology.",
    "winnings": "Gambling / lottery winnings are difficult to evidence.",
    "gift": "Gifted funds require identification of the donor and the donor's own source of funds.",
    "loan from": "Third-party loans require lender identification and loan agreement.",
    "third part": "Third-party funding requires identification of the funder and relationship.",
    "various": "Vague multi-source explanation ('various') lacks specificity.",
    "family": "Family-sourced funds require identification of the family member and their source.",
}
VAGUE = {"business", "savings", "investments", "family", "salary", "income", "work", "personal funds"}
EVIDENCE = {
    "employment": ["Last 3 payslips", "Employment contract or employer letter", "Bank statements showing salary credits"],
    "business": ["Company registry extract", "Latest filed financial statements", "Business bank statements"],
    "savings": ["6-12 months of savings account statements"],
    "pension": ["Pension statement / award letter"],
    "rental": ["Tenancy agreements", "Property title documents"],
    "gift": ["Signed gift letter", "Donor ID and evidence of donor's source of funds"],
    "loan": ["Loan agreement", "Lender identification"],
    "sale": ["Sale and purchase agreement", "Proof of receipt of proceeds"],
    "inheritance": ["Will / grant of probate", "Solicitor letter"],
}


def _heuristics(c: Customer, docs: list) -> dict:
    text = (c.source_of_funds or "").strip()
    low = text.lower()
    score = 50
    obs: list[str] = []
    evidence: list[str] = []

    if len(text) < 25:
        score -= 25
        obs.append("Explanation is very short and does not state the origin of the money.")
    elif len(text) > 80:
        score += 8
    hits_specific = [k for k in SPECIFIC if k in low]
    if hits_specific:
        score += min(20, 8 * len(hits_specific))
    else:
        score -= 10
        obs.append("No concrete funding mechanism (salary, sale, dividend, pension...) is described.")
    if low in VAGUE or all(w in VAGUE for w in low.replace(",", " ").split() if len(w) > 3):
        score -= 15
        obs.append("Explanation relies on generic terms and lacks names, amounts or timeframes.")
    if any(ch.isdigit() for ch in text):
        score += 6
    for kw, msg in RISKY.items():
        if kw in low:
            score -= 8
            if msg not in obs:
                obs.append(msg)

    # income vs. expected activity
    activity = annualised_expected_activity(c.expected_activity)
    income = c.annual_income or 0
    if activity and income:
        ratio = activity / income
        if ratio > 3:
            score -= 25
            obs.append(f"Expected annual activity (~EUR {activity:,.0f}) is {ratio:.1f}x declared income (EUR {income:,.0f}) - unexplained funding gap.")
        elif ratio > 1.5:
            score -= 12
            obs.append(f"Expected annual activity (~EUR {activity:,.0f}) exceeds declared income (EUR {income:,.0f}) by {ratio:.1f}x.")
        else:
            score += 8
    elif not c.expected_activity:
        obs.append("Expected activity not provided - cannot test the explanation against account usage.")

    if any(d.doc_type == "SOF_EVIDENCE" for d in docs):
        score += 15
    else:
        obs.append("No source-of-funds evidence is on file.")

    for key, items in EVIDENCE.items():
        if key in low or (key == "employment" and any(w in low for w in ("salary", "payroll", "wage"))):
            evidence.extend(i for i in items if i not in evidence)
    if not evidence:
        evidence = ["Bank statements (3-6 months)", "Written clarification of the origin of funds"]

    score = max(0, min(100, score))
    label = "PLAUSIBLE" if score >= 65 else "PARTIALLY_PLAUSIBLE" if score >= 40 else "IMPLAUSIBLE"
    return {"score": score, "label": label, "observations": obs, "evidence": evidence}


def run(db, c: Customer, ctx: dict) -> dict:
    h = _heuristics(c, ctx.get("_docs", []))
    result = {
        "plausibility": h["label"],
        "plausibility_score": h["score"],
        "risk_observations": h["observations"],
        "suggested_evidence": h["evidence"],
        "customer_explanation": c.source_of_funds,
        "assessment": (
            f"The source-of-funds explanation is assessed as {h['label'].replace('_', ' ').lower()} (score {h['score']}/100). "
            + (" ".join(h["observations"][:2]) if h["observations"] else "It is specific, consistent with declared income and supported by evidence.")
        ),
        "engine": "rules",
    }

    ai = llm.ask_json(
        "Assess the plausibility of this customer's SOURCE OF FUNDS explanation given their profile and the rule-based findings. "
        'Return JSON: {"plausibility": "PLAUSIBLE|PARTIALLY_PLAUSIBLE|IMPLAUSIBLE", "assessment": "3-4 sentences", '
        '"risk_observations": ["extra observations not already listed"], "suggested_evidence": ["extra evidence requests"]}.\n\n'
        f"<customer_data>\n{customer_facts(c)}\nExplanation: {c.source_of_funds}\nExpected activity: {c.expected_activity}\n</customer_data>\n"
        f"<facts>Rule findings: {h['observations']}; rule plausibility: {h['label']}; evidence on file: {[d.doc_type for d in ctx.get('_docs', [])]}</facts>"
    )
    if ai:
        order = ["IMPLAUSIBLE", "PARTIALLY_PLAUSIBLE", "PLAUSIBLE"]
        ai_label = ai.get("plausibility")
        if ai_label in order:
            # take the more cautious of rules vs Claude
            result["plausibility"] = min(h["label"], ai_label, key=order.index)
        if isinstance(ai.get("assessment"), str):
            result["assessment"] = ai["assessment"]
        for key, target in (("risk_observations", "risk_observations"), ("suggested_evidence", "suggested_evidence")):
            extra = [x for x in ai.get(key, []) if isinstance(x, str) and x not in result[target]]
            result[target] = result[target] + extra[:4]
        result["engine"] = "rules+claude"
    return result
