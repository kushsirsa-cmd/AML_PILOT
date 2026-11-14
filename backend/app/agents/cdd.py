"""CDD Agent: geography, industry, product and channel risk."""
from ..data.risk_tables import (
    CHANNEL_SCORES,
    PRODUCT_SCORES,
    country_risk,
    industry_risk,
    level_from_score,
)
from ..models import Customer
from .base import customer_facts, narrate

# component caps used by the risk engine
CAPS = {"geography": 30, "industry": 25, "product": 25, "channel": 15}


def run(db, c: Customer, ctx: dict) -> dict:
    res = country_risk(c.country_of_residence)
    nat = country_risk(c.nationality)
    nat_weighted = round(nat["score"] * 0.8)
    if res["score"] >= nat_weighted:
        geo_score, geo_basis = res["score"], "country of residence"
    else:
        geo_score, geo_basis = nat_weighted, "nationality"
    # nationality is a weaker signal than residence, so its level is stepped down one notch
    step_down = {"PROHIBITED": "HIGH", "HIGH": "MEDIUM"}
    geo_level = res["level"] if geo_basis == "country of residence" else step_down.get(nat["level"], nat["level"])
    geography = {
        "level": geo_level,
        "score": min(geo_score, CAPS["geography"]),
        "residence": {"country": c.country_of_residence, **res},
        "nationality": {"country": c.nationality, **nat},
        "reason": f"Driven by {geo_basis}: " + (res["reason"] if geo_basis == "country of residence" else nat["reason"]),
        "prohibited_residence": res["level"] == "PROHIBITED",
        "prohibited_nationality": nat["level"] == "PROHIBITED",
    }

    ind = industry_risk(c.industry)
    industry = {**ind, "score": min(ind["score"], CAPS["industry"])}

    p_score = PRODUCT_SCORES.get(c.product, 8)
    product = {
        "level": level_from_score(p_score, 15, 8),
        "score": min(p_score, CAPS["product"]),
        "reason": f"Product '{c.product}' carries a base inherent risk score of {p_score}.",
    }
    ch_score = CHANNEL_SCORES.get(c.channel, 8)
    channel = {
        "level": level_from_score(ch_score, 12, 6),
        "score": min(ch_score, CAPS["channel"]),
        "reason": f"Channel '{c.channel}' carries a base inherent risk score of {ch_score}.",
    }

    total = geography["score"] + industry["score"] + product["score"] + channel["score"]
    max_total = sum(CAPS.values())
    cdd_level = level_from_score(total, 45, 20)
    if geography["prohibited_residence"]:
        cdd_level = "PROHIBITED"

    explanation = [
        f"Geography ({geography['level']}, {geography['score']}): {geography['reason']}",
        f"Industry ({industry['level']}, {industry['score']}): {industry['reason']}",
        f"Product ({product['level']}, {product['score']}): {product['reason']}",
        f"Channel ({channel['level']}, {channel['score']}): {channel['reason']}",
    ]
    fallback = (
        f"Inherent CDD risk is {cdd_level} ({total}/{max_total}). "
        f"Geography is {geography['level']}, industry is {industry['level']}, product is {product['level']} "
        f"and channel is {channel['level']}. "
        + ("Standard CDD measures are sufficient." if cdd_level == "LOW" else
           "Enhanced scrutiny of the highest-scoring factors is recommended." if cdd_level != "PROHIBITED" else
           "The relationship falls into a prohibited jurisdiction and cannot proceed.")
    )
    assessment, engine = narrate(
        "Write a CDD assessment explaining the overall inherent risk and which factors drive it.",
        {"customer": customer_facts(c), "geography": geography, "industry": industry, "product": product,
         "channel": channel, "total": total, "max": max_total, "level": cdd_level},
        fallback,
    )
    return {
        "geography": geography,
        "industry": industry,
        "product": product,
        "channel": channel,
        "cdd_score": total,
        "cdd_max_score": max_total,
        "cdd_level": cdd_level,
        "cdd_assessment": assessment,
        "risk_explanation": explanation,
        "engine": engine,
    }
