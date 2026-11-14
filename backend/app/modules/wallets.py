"""Wallet screening service: runs the analytics, stores the result, updates the wallet and raises alerts."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..agents import pipeline
from ..agents.base import narrate
from ..models import Analysis, Customer, Wallet
from . import chain
from .alerts import raise_alert


def screen_wallet(db: Session, w: Wallet, *, actor: str = "system", graph: chain.ChainGraph | None = None) -> dict:
    g = graph or chain.ChainGraph.load(db)
    res = chain.screen_address(g, w.address)
    top = res["risk_indicators"][:5]
    fallback = (f"Wallet {w.address[:10]}... scores {res['risk_score']}/100 ({res['risk_level']}). "
                + (" ".join(top[:2]) if top else "No risky exposure or suspicious behaviour was found."))
    summary, engine = narrate(
        "Summarise this blockchain risk screening for the compliance analyst (sources of funds, destinations, behaviour).",
        dict(level=res["risk_level"], score=res["risk_score"], exposure=res["exposure"], patterns=[p["detail"] for p in res["patterns"]],
             traces=[(t["category"], t["hops"]) for t in res["risky_traces"]]), fallback)
    res.update(summary=summary, engine=engine, wallet_id=w.id)
    w.risk_score, w.risk_level, w.last_screened_at = res["risk_score"], res["risk_level"], datetime.now(timezone.utc)
    db.add(Analysis(entity_type="wallet", entity_id=w.id, kind="wallet_screening", engine=engine, output=res))
    audit.log(db, actor=f"Crypto Screening Agent ({engine})", actor_type=audit.AI, action="WALLET_SCREENED", entity_type="wallet",
              entity_id=w.id, customer_id=w.customer_id,
              details=dict(requested_by=actor, level=res["risk_level"], score=res["risk_score"], patterns=[p["pattern"] for p in res["patterns"]]))
    if res["risk_level"] in ("HIGH", "SEVERE"):
        raise_alert(db, source="CRYPTO", entity_type="wallet", entity_id=w.id, customer_id=w.customer_id,
                    severity="CRITICAL" if res["risk_level"] == "SEVERE" else "HIGH",
                    title=f"Wallet {w.address[:10]}... risk {res['risk_level']}", description=" | ".join(top) or summary,
                    details=dict(score=res["risk_score"], patterns=[p["pattern"] for p in res["patterns"]]))
    db.flush()
    return res


def refresh_customer_risk(db: Session, customer_id: int | None, actor: str) -> None:
    """Re-score a customer after crypto screening changed (adds the wallet component to the risk engine)."""
    if not customer_id:
        return
    c = db.get(Customer, customer_id)
    if not c:
        return
    ctx = pipeline.load_context(db, c, actor, trigger="CRYPTO_SCREENING")
    if not all(k in ctx for k in pipeline.DEPS["risk"]):
        return
    for name in ("risk", "summary"):
        pipeline.run_agent(db, c, name, ctx, actor=actor)


def latest_screening(db: Session, wallet_id: int) -> dict | None:
    a = db.scalar(select(Analysis).where(Analysis.entity_type == "wallet", Analysis.entity_id == wallet_id,
                                         Analysis.kind == "wallet_screening").order_by(Analysis.id.desc()).limit(1))
    return a.output if a else None
