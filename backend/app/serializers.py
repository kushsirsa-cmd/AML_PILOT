from .models import Assessment, CaseNote, Customer, Document, Review, ScreeningHit


def customer_dict(c: Customer) -> dict:
    return {
        "id": c.id,
        "customer_ref": c.customer_ref,
        "full_name": c.full_name,
        "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None,
        "nationality": c.nationality,
        "country_of_residence": c.country_of_residence,
        "address": c.address,
        "occupation": c.occupation,
        "industry": c.industry,
        "source_of_funds": c.source_of_funds,
        "source_of_wealth": c.source_of_wealth,
        "expected_activity": c.expected_activity,
        "annual_income": c.annual_income,
        "product": c.product,
        "channel": c.channel,
        "pep_declared": c.pep_declared,
        "status": c.status,
        "risk_rating": c.risk_rating,
        "risk_score": c.risk_score,
        "onboarded_at": c.onboarded_at.isoformat() if c.onboarded_at else None,
        "last_kyc_review": c.last_kyc_review.isoformat() if c.last_kyc_review else None,
        "next_review_due": c.next_review_due.isoformat() if c.next_review_due else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def document_dict(d: Document) -> dict:
    return {
        "id": d.id, "doc_type": d.doc_type, "description": d.description,
        "issued_date": d.issued_date.isoformat() if d.issued_date else None,
        "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
    }


def hit_dict(h: ScreeningHit) -> dict:
    return {
        "id": h.id, "customer_id": h.customer_id, "list_type": h.list_type, "entity_id": h.entity_id,
        "matched_name": h.matched_name, "confidence": h.confidence, "disposition": h.disposition,
        "disposition_note": h.disposition_note, "details": h.details,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def review_dict(r: Review) -> dict:
    return {
        "id": r.id, "customer_id": r.customer_id, "review_type": r.review_type, "trigger": r.trigger,
        "status": r.status, "recommendation": r.recommendation, "outcome": r.outcome, "decision": r.decision,
        "decision_note": r.decision_note, "decided_by": r.decided_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def note_dict(n: CaseNote) -> dict:
    return {"id": n.id, "content": n.content, "engine": n.engine, "created_at": n.created_at.isoformat()}


def assessment_dict(a: Assessment) -> dict:
    return {"id": a.id, "agent": a.agent, "engine": a.engine, "output": a.output, "created_at": a.created_at.isoformat()}
