"""Event Driven Review Agent: re-assesses a customer when a trigger event occurs and decides the escalation outcome."""
import hashlib

from .. import audit, llm
from ..data.risk_tables import RATING_ORDER, country_risk, industry_risk
from ..models import Customer, Review
from ..screening_service import load_lists
from . import pipeline
from .screening import effective_confidence, upsert_hit

EVENT_TYPES = ["ADDRESS_CHANGE", "NEW_SANCTIONS_MATCH", "OCCUPATION_CHANGE", "NEW_ADVERSE_MEDIA"]


class EventError(ValueError):
    pass


def _apply_event(db, c: Customer, event_type: str, payload: dict) -> dict:
    """Mutate customer data / watch-list hits to reflect the event. Returns details about the change."""
    if event_type == "ADDRESS_CHANGE":
        new_address, new_country = payload.get("new_address"), payload.get("new_country")
        if not new_address and not new_country:
            raise EventError("ADDRESS_CHANGE requires new_address and/or new_country.")
        change = {"old_address": c.address, "old_country": c.country_of_residence}
        if new_address:
            c.address = new_address
        if new_country:
            c.country_of_residence = new_country
        change.update(new_address=c.address, new_country=c.country_of_residence)
        return change
    if event_type == "OCCUPATION_CHANGE":
        new_occ = payload.get("new_occupation")
        if not new_occ:
            raise EventError("OCCUPATION_CHANGE requires new_occupation.")
        change = {"old_occupation": c.occupation, "old_industry": c.industry}
        c.occupation = new_occ
        if payload.get("new_industry"):
            c.industry = payload["new_industry"]
        change.update(new_occupation=c.occupation, new_industry=c.industry)
        return change
    if event_type == "NEW_SANCTIONS_MATCH":
        entry_id = payload.get("list_entry_id")
        entry = next((e for e in load_lists()["SANCTIONS"] if e["id"] == entry_id), None)
        if not entry:
            raise EventError(f"Unknown sanctions list entry '{entry_id}'. Use an id such as SAN-001.")
        conf = float(payload.get("confidence", 92))
        hit = upsert_hit(
            db, c, "SANCTIONS", entry["id"], entry["name"], conf,
            {"matched_alias": None, "matched_on": {"name_similarity": None, "date_of_birth": "n/a", "nationality": "n/a", "source": "list-update delta screening"},
             "record": {k: v for k, v in entry.items() if k != "aliases"}},
        )
        if hit.disposition == "FALSE_POSITIVE":
            hit.disposition = "OPEN"  # a fresh list update re-opens a previously discounted match
        return {"list_entry": entry["id"], "list": entry["list"], "program": entry["program"], "confidence": conf}
    if event_type == "NEW_ADVERSE_MEDIA":
        headline = payload.get("headline")
        if not headline:
            raise EventError("NEW_ADVERSE_MEDIA requires a headline.")
        severity = payload.get("severity", "HIGH").upper()
        if severity not in ("LOW", "MEDIUM", "HIGH"):
            raise EventError("severity must be LOW, MEDIUM or HIGH.")
        entity_id = "EVT-" + hashlib.sha1(headline.encode()).hexdigest()[:8].upper()
        record = {
            "id": entity_id, "name": c.full_name, "category": payload.get("category", "FRAUD"), "severity": severity,
            "headline": headline, "source": payload.get("source", "Event feed"), "date": payload.get("date"),
        }
        upsert_hit(
            db, c, "ADVERSE_MEDIA", entity_id, c.full_name, float(payload.get("confidence", 85)),
            {"matched_alias": None, "matched_on": {"source": "adverse media monitoring feed"}, "record": record},
        )
        return {"headline": headline, "severity": severity}
    raise EventError(f"Unsupported event type '{event_type}'. Supported: {', '.join(EVENT_TYPES)}")


def decide_escalation(event_type: str, change: dict, before: str | None, after: str, results: dict) -> dict:
    actions: list[str] = []
    rationale: list[str] = []
    outcome, priority = "NO_ESCALATION", "LOW"
    rose = before is not None and RATING_ORDER.index(after) > RATING_ORDER.index(before)

    if event_type == "NEW_SANCTIONS_MATCH":
        conf = change["confidence"]
        if conf >= 90:
            outcome, priority = "ESCALATE_MLRO_FREEZE_PENDING_REVIEW", "CRITICAL"
            actions += ["Restrict account activity pending adjudication", "Notify MLRO / sanctions officer immediately",
                        "Prepare regulatory reporting assessment (freeze / STR as applicable)"]
            rationale.append(f"New sanctions list entry {change['list_entry']} matches at {conf:.0f}% confidence.")
        else:
            outcome, priority = "ESCALATE_SANCTIONS_ANALYST", "HIGH"
            actions += ["Adjudicate potential match with additional identifiers", "Hold new outbound payments until cleared"]
            rationale.append(f"Potential sanctions match at {conf:.0f}% requires adjudication.")
    elif event_type == "NEW_ADVERSE_MEDIA":
        if change["severity"] == "HIGH":
            outcome, priority = "ESCALATE_COMPLIANCE_OFFICER", "HIGH"
            actions += ["Validate article reliability and identity match", "Request customer explanation", "Consider STR / SAR assessment", "Trigger EDD refresh"]
            rationale.append("High-severity adverse media identified.")
        elif change["severity"] == "MEDIUM":
            outcome, priority = "ENHANCED_MONITORING_AND_ANALYST_REVIEW", "MEDIUM"
            actions += ["Analyst to review article and document conclusion", "Apply enhanced monitoring for 6 months"]
            rationale.append("Medium-severity adverse media identified.")
        else:
            outcome, priority = "NOTE_ON_FILE", "LOW"
            actions += ["Record article on file; no further action"]
            rationale.append("Low-severity adverse media.")
    elif event_type == "ADDRESS_CHANGE":
        geo = country_risk(change["new_country"])
        old_geo = country_risk(change["old_country"])
        actions += ["Obtain new proof of address (dated within 3 months)"]
        if geo["level"] == "PROHIBITED":
            outcome, priority = "ESCALATE_MLRO_EXIT_REVIEW", "CRITICAL"
            rationale.append(f"New country {change['new_country']} is a prohibited jurisdiction.")
            actions += ["Suspend new activity; MLRO to decide on exit"]
        elif geo["level"] == "HIGH":
            outcome, priority = "ESCALATE_FOR_EDD", "HIGH"
            rationale.append(f"Customer relocated to high-risk jurisdiction {change['new_country']}.")
            actions += ["Perform EDD refresh", "Establish reasons for relocation and source of funds linkage"]
        elif change["new_country"] != change["old_country"] and geo["score"] > old_geo["score"]:
            outcome, priority = "ANALYST_REVIEW", "MEDIUM"
            rationale.append(f"Relocation from {change['old_country']} to a higher-risk country ({change['new_country']}).")
        else:
            outcome, priority = "UPDATE_RECORDS_NO_ESCALATION", "LOW"
            rationale.append("Address change does not increase geographic risk.")
    elif event_type == "OCCUPATION_CHANGE":
        new_ind = industry_risk(change["new_industry"])
        actions += ["Obtain evidence of new employment / business", "Refresh source of funds and expected activity"]
        if new_ind["level"] == "HIGH":
            outcome, priority = "ESCALATE_FOR_EDD", "HIGH"
            rationale.append(f"New occupation falls in a high-risk sector ({new_ind['category']}).")
        elif change["old_occupation"].strip().lower() != change["new_occupation"].strip().lower():
            outcome, priority = "ANALYST_REVIEW", "MEDIUM" if new_ind["level"] == "MEDIUM" else "LOW"
            rationale.append("Occupation change requires SoF / expected-activity refresh.")

    # the re-scored rating can only push the outcome up, never down
    if after == "PROHIBITED" and priority != "CRITICAL":
        outcome, priority = "ESCALATE_MLRO_EXIT_REVIEW", "CRITICAL"
        rationale.append("Re-scored rating is PROHIBITED.")
    elif rose and after == "HIGH" and priority in ("LOW", "MEDIUM"):
        outcome, priority = "ESCALATE_FOR_EDD", "HIGH"
        rationale.append(f"Risk rating increased {before} -> {after}.")
    elif rose:
        rationale.append(f"Risk rating increased {before} -> {after}.")
    if results["edd"]["edd_required"] and "Perform EDD refresh" not in actions and priority in ("HIGH", "CRITICAL"):
        actions.append("Perform EDD refresh")
    return {"escalation_outcome": outcome, "priority": priority, "actions": actions, "rationale": rationale}


def run(db, c: Customer, event_type: str, payload: dict, *, actor: str = "system") -> Review:
    payload = payload or {}
    before = c.risk_rating
    audit.log(db, actor=actor, actor_type=audit.SYSTEM, action="EVENT_RECEIVED", entity_type="customer",
              entity_id=c.id, customer_id=c.id, details={"event_type": event_type, "payload": payload})
    change = _apply_event(db, c, event_type, payload)
    db.flush()

    results = pipeline.run_full_assessment(db, c, actor=actor, trigger=f"EVENT:{event_type}")
    after = results["risk"]["risk_rating"]
    decision = decide_escalation(event_type, change, before, after, results)

    active_hits = [h for h in results["screening"]["hits"] if h["disposition"] != "FALSE_POSITIVE" and effective_confidence(h) >= 75]
    narrative = llm.ask(
        "Write a 3-4 sentence escalation note for the compliance team about this event-driven review.\n"
        f"<facts>event={event_type}; change={change}; rating {before}->{after}; outcome={decision}; "
        f"active_hits={[(h['list_type'], h['matched_name'], h['confidence']) for h in active_hits]}</facts>",
        max_tokens=350,
    )
    outcome = {
        "event_type": event_type,
        "event_payload": payload,
        "change_applied": change,
        "rating_before": before,
        "rating_after": after,
        "score_after": results["risk"]["risk_score"],
        **decision,
        "narrative": narrative or (" ".join(decision["rationale"]) + f" Outcome: {decision['escalation_outcome'].replace('_', ' ').lower()}."),
        "engine": "rules+claude" if narrative else "rules",
    }
    review = Review(
        customer_id=c.id, review_type="EVENT_DRIVEN", trigger=event_type, status="PENDING",
        recommendation=decision["escalation_outcome"], outcome=outcome,
    )
    db.add(review)
    db.flush()
    audit.log(
        db, actor=f"Event Driven Review Agent ({outcome['engine']})", actor_type=audit.AI, action="EVENT_REVIEW_COMPLETED",
        entity_type="review", entity_id=review.id, customer_id=c.id,
        details={"event_type": event_type, "outcome": decision["escalation_outcome"], "priority": decision["priority"],
                 "rating_before": before, "rating_after": after, "requested_by": actor},
    )
    db.commit()
    return review
