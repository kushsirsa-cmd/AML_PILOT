"""Screening Agent: sanctions, PEP and adverse-media screening against the sample datasets."""
from sqlalchemy import select

from ..models import Customer, ScreeningHit
from ..screening_service import classify, screen
from .base import narrate


def effective_confidence(hit: dict) -> float:
    """Analyst dispositions override the matcher: confirmed = 100, false positive = 0."""
    if hit["disposition"] == "FALSE_POSITIVE":
        return 0.0
    if hit["disposition"] == "CONFIRMED":
        return 100.0
    return float(hit["confidence"])


def hit_to_dict(h: ScreeningHit) -> dict:
    return {
        "id": h.id,
        "list_type": h.list_type,
        "entity_id": h.entity_id,
        "matched_name": h.matched_name,
        "confidence": h.confidence,
        "strength": classify(h.confidence),
        "disposition": h.disposition,
        "disposition_note": h.disposition_note,
        "details": h.details,
    }


def upsert_hit(db, c: Customer, list_type: str, entity_id: str, matched_name: str, confidence: float, details: dict) -> ScreeningHit:
    existing = db.scalar(
        select(ScreeningHit).where(
            ScreeningHit.customer_id == c.id,
            ScreeningHit.list_type == list_type,
            ScreeningHit.entity_id == entity_id,
        )
    )
    if existing:
        existing.confidence = confidence
        existing.matched_name = matched_name
        existing.details = details
        return existing
    hit = ScreeningHit(
        customer_id=c.id, list_type=list_type, entity_id=entity_id,
        matched_name=matched_name, confidence=confidence, details=details,
    )
    db.add(hit)
    db.flush()
    return hit


def run(db, c: Customer, ctx: dict) -> dict:
    results = screen(c.full_name, c.date_of_birth, c.nationality)
    for list_type, hits in results.items():
        for h in hits:
            upsert_hit(
                db, c, list_type, h["entity_id"], h["matched_name"], h["confidence"],
                {"matched_alias": h["matched_alias"], "matched_on": h["matched_on"], "record": h["record"]},
            )
    db.flush()

    all_hits = [hit_to_dict(h) for h in db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == c.id).order_by(ScreeningHit.confidence.desc()))]
    by_type = {t: [h for h in all_hits if h["list_type"] == t] for t in ("SANCTIONS", "PEP", "ADVERSE_MEDIA")}
    active = [h for h in all_hits if h["disposition"] != "FALSE_POSITIVE"]
    top = max((effective_confidence(h) for h in active), default=0.0)
    result = (
        "NO_MATCH" if top < 65 else "WEAK_MATCH" if top < 75 else "POTENTIAL_MATCH" if top < 90 else "STRONG_MATCH"
    )

    indicators: list[str] = []
    for h in active:
        conf = effective_confidence(h)
        rec = h["details"].get("record", {})
        if h["list_type"] == "SANCTIONS" and conf >= 65:
            indicators.append(f"Sanctions {classify(conf).lower()} match ({conf:.0f}%) to '{h['matched_name']}' - {rec.get('list', '')} / {rec.get('program', '')}.")
        elif h["list_type"] == "PEP" and conf >= 65:
            indicators.append(f"PEP {classify(conf).lower()} match ({conf:.0f}%) to '{h['matched_name']}' - {rec.get('position', '')} ({rec.get('pep_type', '')}).")
        elif h["list_type"] == "ADVERSE_MEDIA" and conf >= 65:
            indicators.append(f"Adverse media ({rec.get('severity', '?')} / {rec.get('category', '?')}) {conf:.0f}% match: {rec.get('headline', h['matched_name'])}.")
    if c.pep_declared and not any(h["list_type"] == "PEP" for h in active):
        indicators.append("Customer self-declared as PEP but no PEP list match found - verify position and role.")

    fallback = (
        f"Screening of '{c.full_name}' returned {len(active)} active hit(s) "
        f"(sanctions {sum(1 for h in by_type['SANCTIONS'] if h in active)}, PEP {sum(1 for h in by_type['PEP'] if h in active)}, "
        f"adverse media {sum(1 for h in by_type['ADVERSE_MEDIA'] if h in active)}). "
        f"Overall result: {result.replace('_', ' ')} with a top match confidence of {top:.0f}%."
        + (" Analyst review of each match is required before onboarding can proceed." if active else " No further action required.")
    )
    narrative, engine = narrate(
        "Summarise the screening outcome for the analyst, highlighting which matches look genuine and which look like name coincidences (use the date-of-birth / nationality evidence).",
        {"customer": c.full_name, "result": result, "top_confidence": top, "hits": [
            {k: h[k] for k in ("list_type", "matched_name", "confidence", "disposition")} | {"matched_on": h["details"].get("matched_on")} for h in all_hits]},
        fallback,
    )
    return {
        "screening_result": result,
        "match_confidence_score": round(top, 1),
        "sanctions": by_type["SANCTIONS"],
        "pep": by_type["PEP"],
        "adverse_media": by_type["ADVERSE_MEDIA"],
        "hits": all_hits,
        "risk_indicators": indicators,
        "narrative": narrative,
        "engine": engine,
    }
