"""QA sampling and review of analyst / MLRO decisions: automated pre-checks plus a human four-eyes checklist."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Alert, Assessment, AuditLog, Customer, QaReview, ScreeningHit, Sar
from .sar import narrative_gaps

REVIEWED_ACTIONS = ["CASE_DECISION", "REVIEW_DECISION", "SCREENING_HIT_DISPOSITION", "ALERT_ACTION", "MLRO_DECISION", "SAR_MLRO_DECISION"]

CHECKLISTS = {
    "default": {
        "rationale_documented": "A clear, specific rationale is recorded",
        "decision_supported_by_evidence": "The decision is supported by the evidence on file",
        "policy_followed": "Policy / procedure followed (approvals, escalations, SLAs)",
        "screening_adjudication_correct": "Screening hits correctly adjudicated",
        "risk_rating_appropriate": "Risk rating and EDD level appropriate",
    }
}
CRITICAL_CRITERIA = {"decision_supported_by_evidence", "rationale_documented"}


def _note(d: dict) -> str:
    return (d.get("note") or "").strip()


def precheck(db: Session, row: AuditLog) -> list[dict]:
    """Automated QA findings for one decision. Each finding: category, severity, detail."""
    f: list[dict] = []
    d, act = row.details or {}, row.action

    def add(cat: str, sev: str, detail: str):
        f.append(dict(category=cat, severity=sev, detail=detail))

    if act in ("CASE_DECISION", "REVIEW_DECISION", "ALERT_ACTION", "MLRO_DECISION", "SAR_MLRO_DECISION", "SCREENING_HIT_DISPOSITION"):
        note = _note(d)
        if len(note) < 15:
            add("DOCUMENTATION", "HIGH", f"Rationale is too short to evidence the decision ('{note}').")
        elif len(note.split()) < 4:
            add("DOCUMENTATION", "MEDIUM", "Rationale is a fragment, not an explanation.")
    cust = db.get(Customer, row.customer_id) if row.customer_id else None
    if act == "CASE_DECISION" and cust:
        if d.get("decision") == "APPROVE":
            edd = db.scalar(select(Assessment).where(Assessment.customer_id == cust.id, Assessment.agent == "edd").order_by(Assessment.id.desc()).limit(1))
            kyc = db.scalar(select(Assessment).where(Assessment.customer_id == cust.id, Assessment.agent == "kyc").order_by(Assessment.id.desc()).limit(1))
            if edd and edd.output["edd_recommendation"] == "SENIOR_MANAGEMENT_APPROVAL_REQUIRED":
                add("POLICY_BREACH", "HIGH", "Approved a PEP / senior-approval case without evidence of senior management sign-off in the rationale.")
            if edd and edd.output["edd_required"] and cust.risk_rating == "HIGH" and "edd" not in _note(d).lower() and "enhanced" not in _note(d).lower():
                add("DECISION_QUALITY", "MEDIUM", "HIGH-risk approval does not reference EDD measures performed.")
            if kyc and kyc.output["missing_information"]:
                add("DECISION_QUALITY", "MEDIUM", f"Approved with {len(kyc.output['missing_information'])} KYC item(s) still missing.")
        if d.get("decision") == "REJECT" and cust.risk_rating == "LOW":
            add("DECISION_QUALITY", "MEDIUM", "Rejected a LOW-risk customer - check rationale for de-risking bias.")
    if act == "SCREENING_HIT_DISPOSITION" and d.get("to") == "FALSE_POSITIVE" and row.entity_id:
        h = db.get(ScreeningHit, int(row.entity_id))
        if h:
            m = (h.details or {}).get("matched_on", {})
            if (m.get("name_similarity") or 0) >= 95 and m.get("date_of_birth") == "exact":
                add("DECISION_QUALITY", "HIGH", "Cleared as false positive although name is near-identical AND date of birth matches exactly.")
            elif h.confidence >= 90:
                add("DECISION_QUALITY", "HIGH", f"Cleared a {h.confidence:.0f}% confidence match as false positive.")
    if act == "REVIEW_DECISION" and d.get("decision", "").startswith("COMPLETE") and cust:
        from ..models import Review
        rv = db.get(Review, int(row.entity_id)) if row.entity_id else None
        if rv and (rv.outcome.get("missing_documents") or rv.outcome.get("expired_documents")):
            add("POLICY_BREACH", "HIGH", "Review completed while documents were still missing or expired.")
        if rv and rv.outcome.get("priority") == "CRITICAL" and d["decision"].startswith("COMPLETE"):
            add("POLICY_BREACH", "HIGH", "CRITICAL-priority event review closed without escalation.")
    if act == "ALERT_ACTION" and d.get("action") == "CLOSE":
        al = db.get(Alert, int(row.entity_id)) if row.entity_id else None
        if al and al.severity in ("HIGH", "CRITICAL"):
            add("POLICY_BREACH", "HIGH", f"{al.severity} alert closed at analyst level instead of MLRO escalation.")
    if act == "SAR_MLRO_DECISION" and row.entity_id:
        sar = db.get(Sar, int(row.entity_id))
        if sar:
            gaps = narrative_gaps(sar.narrative)
            if gaps:
                add("DOCUMENTATION", "HIGH", "SAR narrative missing section(s): " + ", ".join(gaps))
            if not sar.typologies:
                add("DECISION_QUALITY", "MEDIUM", "SAR has no typology / predicate indicators mapped.")
    return f


def describe(row: AuditLog) -> str:
    d = row.details or {}
    bits = [row.action.replace("_", " ").title()]
    for k in ("decision", "action", "to", "outcome"):
        if d.get(k):
            bits.append(str(d[k]))
    return " - ".join(bits[:2]) + (f": {_note(d)[:120]}" if _note(d) else "")


def sample(db: Session, *, days: int = 30, low_risk_rate: float = 0.25, actor: str = "qa-sampler") -> list[QaReview]:
    """Risk-weighted sampling: 100% of HIGH/PROHIBITED decisions, SAR decisions and CRITICAL items; `low_risk_rate` of the rest."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    already = set(db.scalars(select(QaReview.audit_id)))
    created = []
    step = max(1, round(1 / low_risk_rate)) if low_risk_rate > 0 else 10**9
    for row in db.scalars(select(AuditLog).where(AuditLog.action.in_(REVIEWED_ACTIONS), AuditLog.actor_type == "USER").order_by(AuditLog.id)):
        ts = row.ts if row.ts.tzinfo else row.ts.replace(tzinfo=timezone.utc)
        if ts < since or row.id in already:
            continue
        cust = db.get(Customer, row.customer_id) if row.customer_id else None
        rating = cust.risk_rating if cust else None
        must = rating in ("HIGH", "PROHIBITED") or row.action in ("SAR_MLRO_DECISION", "MLRO_DECISION") or (row.details or {}).get("priority") == "CRITICAL"
        findings = precheck(db, row)
        if not (must or findings or row.id % step == 0):
            continue
        q = QaReview(audit_id=row.id, decision_action=row.action, decision_maker=row.actor, customer_id=row.customer_id, risk_rating=rating,
                     summary=describe(row), precheck=findings)
        db.add(q)
        created.append(q)
    db.flush()
    return created


def complete(q: QaReview, reviewer: str, checklist: dict[str, str], findings: str | None) -> QaReview:
    valid = set(CHECKLISTS["default"])
    if set(checklist) - valid:
        raise ValueError(f"Unknown criteria: {sorted(set(checklist) - valid)}")
    if any(v not in ("PASS", "FAIL", "NA") for v in checklist.values()):
        raise ValueError("Checklist values must be PASS, FAIL or NA.")
    if set(checklist) != valid:
        raise ValueError("All criteria must be answered: " + ", ".join(sorted(valid)))
    if reviewer.strip().lower() == q.decision_maker.strip().lower():
        raise PermissionError("QA reviewer must be different from the person who made the decision (four-eyes).")
    scored = [v for v in checklist.values() if v != "NA"]
    fails = [k for k, v in checklist.items() if v == "FAIL"]
    if any(k in CRITICAL_CRITERIA for k in fails) or len(fails) >= 2:
        outcome = "FAIL"
    elif fails:
        outcome = "PASS_WITH_FINDINGS"
    else:
        outcome = "PASS"
    if fails and not (findings and findings.strip()):
        raise ValueError("Findings text is required when any criterion fails.")
    q.checklist, q.findings, q.reviewer = checklist, findings, reviewer
    q.score = round(100 * sum(1 for v in scored if v == "PASS") / len(scored), 1) if scored else None
    q.outcome, q.status, q.completed_at = outcome, "COMPLETED", datetime.now(timezone.utc)
    return q


def dashboard(db: Session) -> dict:
    rows = list(db.scalars(select(QaReview)))
    done = [r for r in rows if r.status == "COMPLETED"]
    pending = [r for r in rows if r.status == "PENDING"]
    now = datetime.now(timezone.utc)
    aw = lambda t: t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    by_maker: dict[str, dict] = defaultdict(lambda: dict(sampled=0, completed=0, failed=0, with_findings=0, auto_flags=0))
    for r in rows:
        m = by_maker[r.decision_maker]
        m["sampled"] += 1
        m["auto_flags"] += len(r.precheck)
        if r.status == "COMPLETED":
            m["completed"] += 1
            m["failed"] += r.outcome == "FAIL"
            m["with_findings"] += r.outcome == "PASS_WITH_FINDINGS"
    for m in by_maker.values():
        m["error_rate_pct"] = round(100 * (m["failed"] + m["with_findings"]) / m["completed"], 1) if m["completed"] else None
    cat = Counter(f["category"] for r in rows for f in r.precheck)
    crit_fail = Counter(k for r in done for k, v in r.checklist.items() if v == "FAIL")
    by_action = Counter(r.decision_action for r in rows)
    weeks: dict[str, dict] = {}
    for r in done:
        wk = aw(r.completed_at).strftime("%G-W%V")
        w = weeks.setdefault(wk, dict(week=wk, completed=0, passed=0))
        w["completed"] += 1
        w["passed"] += r.outcome == "PASS"
    return dict(
        sampled=len(rows), completed=len(done), pending=len(pending),
        pass_rate_pct=round(100 * sum(r.outcome == "PASS" for r in done) / len(done), 1) if done else None,
        outcomes=dict(Counter(r.outcome for r in done)), avg_score=round(sum(r.score or 0 for r in done) / len(done), 1) if done else None,
        auto_flagged=sum(1 for r in rows if r.precheck), auto_findings_by_category=dict(cat), failed_criteria=dict(crit_fail),
        by_decision_type=dict(by_action), by_analyst=[dict(analyst=k, **v) for k, v in sorted(by_maker.items())],
        oldest_pending_days=max(((now - aw(r.created_at)).days for r in pending), default=0),
        weekly_trend=[dict(w, pass_rate_pct=round(100 * w["passed"] / w["completed"], 1)) for _, w in sorted(weeks.items())][-8:],
    )


def qa_dict(q: QaReview) -> dict:
    return dict(id=q.id, audit_id=q.audit_id, decision_action=q.decision_action, decision_maker=q.decision_maker, customer_id=q.customer_id,
                risk_rating=q.risk_rating, summary=q.summary, status=q.status, precheck=q.precheck, checklist=q.checklist, score=q.score,
                outcome=q.outcome, findings=q.findings, reviewer=q.reviewer, created_at=q.created_at.isoformat(),
                completed_at=q.completed_at.isoformat() if q.completed_at else None)
