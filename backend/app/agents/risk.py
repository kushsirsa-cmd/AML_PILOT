"""Risk Rating Engine: transparent additive scoring with hard overrides."""
from datetime import date

from dateutil.relativedelta import relativedelta

from .. import audit
from ..data.risk_tables import RATING_ORDER, REVIEW_CYCLE_MONTHS
from ..models import Customer
from .screening import effective_confidence

THRESHOLDS = {"HIGH": 60, "MEDIUM": 30}
SEVERITY_POINTS = {"HIGH": 20, "MEDIUM": 10, "LOW": 5}
PLAUSIBILITY_POINTS = {"PLAUSIBLE": 0, "PARTIALLY_PLAUSIBLE": 7, "IMPLAUSIBLE": 15}
SOW_POINTS = {"SUFFICIENT": 0, "PARTIAL": 7, "INSUFFICIENT": 15}


def rating_from_score(score: int) -> str:
    return "HIGH" if score >= THRESHOLDS["HIGH"] else "MEDIUM" if score >= THRESHOLDS["MEDIUM"] else "LOW"


def next_review_date(rating: str, last: date | None) -> date | None:
    months = REVIEW_CYCLE_MONTHS.get(rating)
    if not months:
        return None
    return (last or date.today()) + relativedelta(months=months)


def compute(c: Customer, ctx: dict) -> dict:
    kyc, cdd, scr, sof, sow = ctx["kyc"], ctx["cdd"], ctx["screening"], ctx["sof"], ctx["sow"]
    active = [h for h in scr["hits"] if h["disposition"] != "FALSE_POSITIVE"]

    comps: dict[str, dict] = {}

    def add(key: str, points: int, why: str):
        comps[key] = {"points": points, "reason": why}

    add("geography", cdd["geography"]["score"] if cdd["geography"]["level"] != "PROHIBITED" else 30, cdd["geography"]["reason"])
    add("industry", cdd["industry"]["score"], cdd["industry"]["reason"])
    add("product", cdd["product"]["score"], cdd["product"]["reason"])
    add("channel", cdd["channel"]["score"], cdd["channel"]["reason"])

    pep_hits = [h for h in active if h["list_type"] == "PEP" and effective_confidence(h) >= 75]
    is_pep = c.pep_declared or bool(pep_hits)
    add("pep", 25 if is_pep else 0, "PEP / RCA status identified." if is_pep else "No PEP indicators.")

    sanc = [(h, effective_confidence(h)) for h in active if h["list_type"] == "SANCTIONS"]
    top_sanc = max((conf for _, conf in sanc), default=0)
    if top_sanc >= 90:
        add("sanctions", 40, f"Strong sanctions match ({top_sanc:.0f}%).")
    elif top_sanc >= 75:
        add("sanctions", 20, f"Potential sanctions match ({top_sanc:.0f}%) pending adjudication.")
    elif top_sanc >= 65:
        add("sanctions", 5, f"Weak sanctions name similarity ({top_sanc:.0f}%).")
    else:
        add("sanctions", 0, "No sanctions matches.")

    media_pts, media_notes = 0, []
    for h in active:
        if h["list_type"] == "ADVERSE_MEDIA" and effective_confidence(h) >= 75:
            sev = h["details"].get("record", {}).get("severity", "MEDIUM")
            media_pts += SEVERITY_POINTS.get(sev, 10)
            media_notes.append(f"{sev}: {h['details'].get('record', {}).get('headline', h['matched_name'])}")
    add("adverse_media", min(media_pts, 30), "; ".join(media_notes) if media_notes else "No adverse media.")

    add("source_of_funds", PLAUSIBILITY_POINTS.get(sof["plausibility"], 7), f"SoF assessed {sof['plausibility']}.")
    add("source_of_wealth", SOW_POINTS.get(sow["sow_assessment"], 7), f"SoW assessed {sow['sow_assessment']}.")
    kyc_pts = min(20, 3 * len(kyc["missing_information"]) + 2 * len(kyc["kyc_risk_notes"]))
    add("kyc_quality", kyc_pts, f"{len(kyc['missing_information'])} missing item(s), {len(kyc['kyc_risk_notes'])} KYC risk note(s).")

    crypto = ctx.get("_crypto")
    if crypto:
        add("crypto_exposure", crypto["points"], crypto["reason"])

    score = min(100, sum(v["points"] for v in comps.values()))
    rating = rating_from_score(score)
    overrides: list[str] = []

    def floor(level: str, why: str):
        nonlocal rating
        if RATING_ORDER.index(level) > RATING_ORDER.index(rating):
            rating = level
        overrides.append(f"{why} -> minimum rating {level}")

    if is_pep:
        floor("HIGH", "PEP / RCA relationship")
    if crypto and crypto.get("severe"):
        floor("HIGH", "Wallet with SEVERE blockchain risk")
    if cdd["geography"]["prohibited_nationality"]:
        floor("HIGH", "Nationality of a prohibited jurisdiction")
    if cdd["geography"]["prohibited_residence"]:
        floor("PROHIBITED", "Residence in a prohibited jurisdiction")
    if top_sanc >= 90:
        floor("PROHIBITED", "Strong / confirmed sanctions match")

    reasoning = [
        f"{k.replace('_', ' ').title()}: +{v['points']} - {v['reason']}" for k, v in comps.items() if v["points"] > 0
    ] or ["No risk factors scored."]
    reasoning.append(f"Total score {score}/100 -> {rating_from_score(score)} (LOW <30, MEDIUM 30-59, HIGH >=60).")
    reasoning.extend(f"Override: {o}" for o in overrides)

    return {
        "risk_rating": rating,
        "risk_score": score,
        "components": comps,
        "overrides": overrides,
        "reasoning": reasoning,
        "thresholds": {"LOW": "<30", "MEDIUM": "30-59", "HIGH": ">=60", "PROHIBITED": "override only"},
    }


def crypto_component(db, c: Customer) -> dict | None:
    from sqlalchemy import select

    from ..models import Wallet

    wallets = list(db.scalars(select(Wallet).where(Wallet.customer_id == c.id, Wallet.risk_level.is_not(None))))
    if not wallets:
        return None
    pts = {"SEVERE": 30, "HIGH": 15, "MEDIUM": 5, "LOW": 0}
    worst = max(wallets, key=lambda w: pts.get(w.risk_level, 0))
    return {"points": pts.get(worst.risk_level, 0), "severe": worst.risk_level == "SEVERE",
            "reason": f"{len(wallets)} screened wallet(s); worst is {worst.risk_level} ({worst.address[:10]}..., score {worst.risk_score})."}


def run(db, c: Customer, ctx: dict) -> dict:
    ctx["_crypto"] = crypto_component(db, c)
    out = compute(c, ctx)
    previous = c.risk_rating
    new = out["risk_rating"]
    actor = ctx.get("_actor", "risk-engine")

    c.risk_rating = new
    c.risk_score = out["risk_score"]
    c.next_review_due = next_review_date(new, c.last_kyc_review or c.onboarded_at)
    if new != previous:
        audit.log(
            db, actor=actor, actor_type=audit.AI,
            action="RISK_RATING_ASSIGNED" if previous is None else "RISK_RATING_CHANGED",
            entity_type="customer", entity_id=c.id, customer_id=c.id,
            details={"from": previous, "to": new, "score": out["risk_score"], "trigger": ctx.get("_trigger", "MANUAL")},
        )
    out["previous_rating"] = previous
    out["rating_changed"] = previous is not None and previous != new
    out["engine"] = "rules"
    return out
