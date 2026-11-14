"""Orchestrates the agents: dependency resolution, persistence and audit logging."""
from sqlalchemy import select

from .. import audit
from ..models import Assessment, CaseNote, Customer
from . import cdd, edd, kyc, risk, screening, sof, sow, summary

ORDER = ["kyc", "screening", "cdd", "edd", "sof", "sow", "risk", "summary"]
RUNNERS = {
    "kyc": kyc.run, "screening": screening.run, "cdd": cdd.run, "edd": edd.run,
    "sof": sof.run, "sow": sow.run, "risk": risk.run, "summary": summary.run,
}
DEPS = {
    "edd": ["cdd", "screening"],
    "risk": ["kyc", "cdd", "screening", "edd", "sof", "sow"],
    "summary": ["kyc", "cdd", "screening", "edd", "sof", "sow", "risk"],
}
LABELS = {
    "kyc": "KYC Agent", "screening": "Screening Agent", "cdd": "CDD Agent", "edd": "EDD Agent",
    "sof": "Source of Funds Agent", "sow": "Source of Wealth Agent", "risk": "Risk Rating Engine",
    "summary": "AI Case Summary Agent",
}


def load_context(db, c: Customer, actor: str, trigger: str = "MANUAL") -> dict:
    ctx: dict = {"_docs": list(c.documents), "_actor": actor, "_trigger": trigger}
    for name in ORDER:
        row = db.scalar(
            select(Assessment).where(Assessment.customer_id == c.id, Assessment.agent == name).order_by(Assessment.id.desc()).limit(1)
        )
        if row:
            ctx[name] = row.output
    return ctx


def run_agent(db, c: Customer, name: str, ctx: dict, *, actor: str = "system") -> dict:
    if name not in RUNNERS:
        raise KeyError(name)
    for dep in DEPS.get(name, []):
        if dep not in ctx:
            run_agent(db, c, dep, ctx, actor=actor)
    output = RUNNERS[name](db, c, ctx)
    engine = output.get("engine", "rules")
    db.add(Assessment(customer_id=c.id, agent=name, engine=engine, output=output))
    if name == "screening":
        from ..modules.alerts import sync_screening_alerts

        db.flush()
        sync_screening_alerts(db, c.id)
    if name == "summary":
        db.add(CaseNote(customer_id=c.id, content=output["case_note"], engine=engine))
    ctx[name] = output
    audit.log(
        db, actor=f"{LABELS[name]} ({engine})", actor_type=audit.AI, action="AGENT_RUN",
        entity_type="assessment", entity_id=name, customer_id=c.id,
        details={"agent": name, "engine": engine, "requested_by": actor, "trigger": ctx.get("_trigger", "MANUAL")},
    )
    db.flush()
    return output


def run_full_assessment(db, c: Customer, *, actor: str = "system", trigger: str = "MANUAL") -> dict:
    """Run every agent in order on fresh data and commit."""
    ctx: dict = {"_docs": list(c.documents), "_actor": actor, "_trigger": trigger}
    for name in ORDER:
        run_agent(db, c, name, ctx, actor=actor)
    db.commit()
    return {k: v for k, v in ctx.items() if not k.startswith("_")}


def run_single(db, c: Customer, name: str, *, actor: str) -> dict:
    ctx = load_context(db, c, actor)
    out = run_agent(db, c, name, ctx, actor=actor)
    db.commit()
    return out
