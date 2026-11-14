"""Periodic Review Agent: missing / expired documents, overdue KYC, risk drift."""
from datetime import date

from dateutil.relativedelta import relativedelta

from .. import audit, llm
from ..data.risk_tables import RATING_ORDER, REQUIRED_DOCS, REVIEW_CYCLE_MONTHS
from ..models import Customer, Review
from . import pipeline


def run(db, c: Customer, *, actor: str = "system") -> Review:
    today = date.today()
    previous = c.risk_rating
    previous_score = c.risk_score

    # refresh all assessments so risk drift is measured on current data
    results = pipeline.run_full_assessment(db, c, actor=actor, trigger="PERIODIC_REVIEW")
    rating = results["risk"]["risk_rating"]

    required = REQUIRED_DOCS.get(rating, REQUIRED_DOCS["MEDIUM"])
    docs = list(c.documents)
    have = {d.doc_type for d in docs}
    missing_docs = [d for d in required if d not in have]
    expired_docs = [
        {"doc_type": d.doc_type, "expired_on": d.expiry_date.isoformat()}
        for d in docs if d.expiry_date and d.expiry_date < today
    ]
    expired_types = {e["doc_type"] for e in expired_docs}
    # an expired document only counts as "missing" if no valid replacement exists
    valid = {d.doc_type for d in docs if not d.expiry_date or d.expiry_date >= today}
    replace_needed = sorted(expired_types - valid)

    months = REVIEW_CYCLE_MONTHS.get(rating)
    last = c.last_kyc_review or c.onboarded_at
    due = (last + relativedelta(months=months)) if (last and months) else None
    kyc_expired = bool(due and due < today)
    if not last and c.status == "ACTIVE":
        kyc_expired = True

    risk_changed = previous is not None and previous != rating
    risk_up = risk_changed and RATING_ORDER.index(rating) > RATING_ORDER.index(previous)
    findings = {
        "missing_documents": missing_docs,
        "expired_documents": expired_docs,
        "documents_requiring_replacement": replace_needed,
        "kyc_review_due": due.isoformat() if due else None,
        "kyc_expired": kyc_expired,
        "previous_rating": previous,
        "current_rating": rating,
        "previous_score": previous_score,
        "current_score": results["risk"]["risk_score"],
        "risk_changed": risk_changed,
        "risk_increased": bool(risk_up),
        "review_cycle_months": months,
        "kyc_missing_information": results["kyc"]["missing_information"],
    }

    reasons: list[str] = []
    if rating == "PROHIBITED":
        rec = "EXIT_RELATIONSHIP_ESCALATE_MLRO"
        reasons.append("Customer now rates PROHIBITED.")
    elif risk_up or rating == "HIGH" or results["edd"]["edd_required"]:
        rec = "ESCALATE_FOR_EDD_REVIEW"
        reasons.append("Risk increased." if risk_up else "Customer is HIGH risk / EDD triggers present.")
    elif missing_docs or replace_needed or results["kyc"]["missing_information"]:
        rec = "REQUEST_DOCUMENTS_AND_INFORMATION"
        reasons.append("Required documents or KYC information are missing or expired.")
    elif kyc_expired:
        rec = "REFRESH_KYC_AND_COMPLETE_REVIEW"
        reasons.append("KYC refresh date has passed.")
    else:
        rec = "COMPLETE_REVIEW_NO_CHANGE"
        reasons.append("No adverse changes detected; documents and KYC are current.")
    if missing_docs:
        reasons.append("Missing: " + ", ".join(missing_docs))
    if replace_needed:
        reasons.append("Expired with no valid replacement: " + ", ".join(replace_needed))
    if risk_changed:
        reasons.append(f"Risk rating moved {previous} -> {rating}.")
    if kyc_expired:
        reasons.append(f"KYC review was due on {due}.")

    narrative = llm.ask(
        "Write a 3-4 sentence periodic-review recommendation for the analyst based on these findings. "
        f"The recommendation code is {rec}.\n<facts>{findings}\nReasons: {reasons}</facts>",
        max_tokens=350,
    )
    outcome = {
        **findings,
        "recommendation": rec,
        "reasons": reasons,
        "narrative": narrative or (" ".join(reasons) + f" Recommended action: {rec.replace('_', ' ').lower()}."),
        "engine": "rules+claude" if narrative else "rules",
    }
    review = Review(
        customer_id=c.id, review_type="PERIODIC", trigger="SCHEDULED_PERIODIC_REVIEW",
        status="PENDING", recommendation=rec, outcome=outcome,
    )
    db.add(review)
    db.flush()
    audit.log(
        db, actor=f"Periodic Review Agent ({outcome['engine']})", actor_type=audit.AI, action="PERIODIC_REVIEW_COMPLETED",
        entity_type="review", entity_id=review.id, customer_id=c.id,
        details={"recommendation": rec, "requested_by": actor, "rating": rating, "previous_rating": previous},
    )
    db.commit()
    return review
