"""Source of Wealth Agent: assesses the wealth narrative and lists missing corroborating evidence."""
from .. import llm
from ..models import Customer
from .base import customer_facts

CATEGORIES = {
    "EMPLOYMENT": (("salary", "employment", "career", "employed", "bonus", "engineer", "manager", "worked"),
                   ["Employment history / CV", "Tax returns for the last 3 years", "Payslips or employer reference letter"]),
    "BUSINESS_OWNERSHIP": (("founded", "own company", "owner of", "my business", "shareholder", "share sale", "sold my", "co-founder", "dividend"),
                           ["Company registry extract and shareholding structure", "Audited / filed financial statements (3 years)", "Share sale agreement or dividend vouchers"]),
    "INHERITANCE": (("inherit", "estate", "probate", "bequest", "will of"),
                    ["Will or grant of probate", "Solicitor / executor confirmation letter", "Evidence of deceased's source of wealth if material"]),
    "PROPERTY": (("property", "real estate", "sale of house", "sale of apartment", "rental income", "flat"),
                 ["Title deeds / land registry extract", "Sale contract and proof of proceeds received"]),
    "INVESTMENTS": (("investment", "portfolio", "shares", "stocks", "brokerage", "fund", "etf"),
                    ["Brokerage / custody statements", "Realised gains tax statements"]),
    "CRYPTO": (("crypto", "bitcoin", "ethereum", "token", "mining", "defi"),
               ["Exchange account statements and trade history", "Wallet addresses with on-chain provenance report", "Fiat on/off-ramp bank records"]),
    "GIFT": (("gift", "donation", "given by", "family support"),
             ["Signed gift letter", "Donor identification and donor's source of wealth"]),
    "GAMBLING_LOTTERY": (("lottery", "gambling", "winnings", "casino"),
                         ["Official winning notice / payout records", "Bank records showing receipt of winnings"]),
    "PENSION_SAVINGS": (("pension", "retire", "savings", "accumulated"),
                        ["Pension statements", "Long-term savings account statements"]),
}


def run(db, c: Customer, ctx: dict) -> dict:
    text = (c.source_of_wealth or "").strip()
    low = text.lower()
    docs = ctx.get("_docs", [])
    has_evidence = any(d.doc_type == "SOW_EVIDENCE" for d in docs)

    found = [name for name, (kws, _) in CATEGORIES.items() if any(k in low for k in kws)]
    missing: list[str] = []
    for name in found:
        missing.extend(e for e in CATEGORIES[name][1] if e not in missing)
    if not found:
        missing = ["Written wealth narrative with timeline, amounts and origin", "Bank / tax records evidencing accumulation of wealth"]
    missing_listed = list(missing)

    score = 20
    obs: list[str] = []
    if len(text) >= 80:
        score += 20
    elif len(text) < 25:
        obs.append("Wealth narrative is too brief to assess.")
    else:
        score += 8
    if found:
        score += min(20, 10 * len(found))
    else:
        obs.append("No recognisable wealth-generating activity is described.")
    if any(ch.isdigit() for ch in text):
        score += 10
    else:
        obs.append("Narrative contains no dates, amounts or timeframes.")
    if c.annual_income and c.annual_income >= 150000 and not any(k in found for k in ("BUSINESS_OWNERSHIP", "INVESTMENTS", "INHERITANCE", "PROPERTY", "EMPLOYMENT")):
        obs.append("High declared income is not matched by a clearly explained wealth-generating source.")
        score -= 10
    if "CRYPTO" in found:
        obs.append("Crypto-derived wealth: provenance is hard to verify; apply enhanced scrutiny.")
        score -= 8
    if "GAMBLING_LOTTERY" in found or "GIFT" in found:
        obs.append("Wealth derived from gifts / winnings carries elevated risk and needs third-party corroboration.")
        score -= 8
    if has_evidence:
        score += 25
        missing = [f"Corroboration still required: {m}" for m in missing[:2]]  # evidence on file but not specific
    else:
        obs.append("No source-of-wealth evidence is on file.")

    score = max(0, min(100, score))
    label = "SUFFICIENT" if score >= 70 else "PARTIAL" if score >= 40 else "INSUFFICIENT"
    result = {
        "sow_assessment": label,
        "sow_score": score,
        "wealth_sources_identified": found,
        "missing_evidence": missing if has_evidence else missing_listed,
        "observations": obs,
        "customer_narrative": c.source_of_wealth,
        "assessment": (
            f"Source of wealth is assessed as {label.lower()} (score {score}/100). "
            + (f"Identified sources: {', '.join(n.replace('_', ' ').lower() for n in found)}. " if found else "")
            + (f"{len(missing_listed)} item(s) of corroborating evidence are outstanding." if not has_evidence else "Some evidence is on file; further corroboration is recommended.")
        ),
        "engine": "rules",
    }

    ai = llm.ask_json(
        "Assess the customer's SOURCE OF WEALTH narrative: is it coherent, proportionate to their age, occupation and income, and verifiable? "
        'Return JSON: {"sow_assessment": "SUFFICIENT|PARTIAL|INSUFFICIENT", "assessment": "3-4 sentences", '
        '"observations": ["extra observations"], "missing_evidence": ["extra evidence the analyst should request"]}.\n\n'
        f"<customer_data>\n{customer_facts(c)}\nWealth narrative: {c.source_of_wealth}\n</customer_data>\n"
        f"<facts>Rule findings: {obs}; rule rating: {label}; evidence on file: {[d.doc_type for d in docs]}</facts>"
    )
    if ai:
        order = ["INSUFFICIENT", "PARTIAL", "SUFFICIENT"]
        if ai.get("sow_assessment") in order:
            result["sow_assessment"] = min(label, ai["sow_assessment"], key=order.index)
        if isinstance(ai.get("assessment"), str):
            result["assessment"] = ai["assessment"]
        for key in ("observations", "missing_evidence"):
            extra = [x for x in ai.get(key, []) if isinstance(x, str) and x not in result[key]]
            result[key] = result[key] + extra[:4]
        result["engine"] = "rules+claude"
    return result
