"""Transaction monitoring rules for fiat / account activity (the crypto equivalent is modules/chain.py)."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.risk_tables import HIGH_RISK_COUNTRIES, PROHIBITED_COUNTRIES
from ..models import Corporate, Customer, Transaction
from .alerts import raise_alert

RULES = {
    "STRUCTURING_CASH": ("HIGH", "Three or more cash deposits of EUR 7,000-9,999 within 14 days (just under reporting thresholds)."),
    "HIGH_RISK_GEOGRAPHY": ("HIGH", "Wire of EUR 5,000+ to or from a high-risk / prohibited jurisdiction."),
    "LARGE_VS_PROFILE": ("MEDIUM", "90-day inflows far exceed the declared income / turnover profile."),
    "RAPID_PASS_THROUGH": ("HIGH", "At least 85% of a large inflow (EUR 20,000+) left the account within 48 hours."),
    "LARGE_CASH": ("MEDIUM", "Single cash transaction of EUR 10,000 or more."),
    "ROUND_AMOUNT_CLUSTER": ("MEDIUM", "Four or more round-sum (multiples of EUR 5,000) transactions within 30 days."),
}


def _aware(t):
    from datetime import timezone

    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def evaluate(txs: list[Transaction], annual_profile: float | None) -> dict[str, list[Transaction]]:
    """Returns rule -> transactions that triggered it for one customer / corporate."""
    txs = sorted(txs, key=lambda t: _aware(t.ts))
    hits: dict[str, list[Transaction]] = defaultdict(list)
    cash_in = [t for t in txs if t.channel == "CASH" and t.direction == "IN" and 7000 <= t.amount_eur < 10000]
    for i, t in enumerate(cash_in):
        window = [x for x in cash_in if timedelta(0) <= _aware(x.ts) - _aware(t.ts) <= timedelta(days=14)]
        if len(window) >= 3:
            hits["STRUCTURING_CASH"] = window
            break
    for t in txs:
        if t.channel in ("WIRE", "SEPA") and t.amount_eur >= 5000 and (t.counterparty_country.lower() in HIGH_RISK_COUNTRIES | PROHIBITED_COUNTRIES):
            hits["HIGH_RISK_GEOGRAPHY"].append(t)
        if t.channel == "CASH" and t.amount_eur >= 10000:
            hits["LARGE_CASH"].append(t)
    if txs:
        last = _aware(txs[-1].ts)
        recent_in = sum(t.amount_eur for t in txs if t.direction == "IN" and last - _aware(t.ts) <= timedelta(days=90))
        if annual_profile and recent_in > max(2.5 * annual_profile / 4, 15000) + 10000:
            hits["LARGE_VS_PROFILE"] = [t for t in txs if t.direction == "IN" and last - _aware(t.ts) <= timedelta(days=90)]
    for t in txs:
        if t.direction == "IN" and t.amount_eur >= 20000:
            out = [x for x in txs if x.direction == "OUT" and timedelta(0) <= _aware(x.ts) - _aware(t.ts) <= timedelta(hours=48)]
            if sum(x.amount_eur for x in out) >= 0.85 * t.amount_eur:
                hits["RAPID_PASS_THROUGH"] = [t, *out]
                break
    rnd = [t for t in txs if t.amount_eur >= 5000 and t.amount_eur % 5000 == 0]
    for t in rnd:
        window = [x for x in rnd if timedelta(0) <= _aware(x.ts) - _aware(t.ts) <= timedelta(days=30)]
        if len(window) >= 4:
            hits["ROUND_AMOUNT_CLUSTER"] = window
            break
    return hits


def monitor(db: Session, actor: str = "txn-monitoring") -> dict:
    """Re-evaluate every entity's transactions, set txn flags and raise de-duplicated alerts."""
    by_cust: dict[int, list[Transaction]] = defaultdict(list)
    by_corp: dict[int, list[Transaction]] = defaultdict(list)
    for t in db.scalars(select(Transaction)):
        t.flags = []
        (by_cust[t.customer_id] if t.customer_id else by_corp[t.corporate_id]).append(t)
    raised = 0
    for cid, txs in by_cust.items():
        c = db.get(Customer, cid)
        _apply(db, txs, c.annual_income, "customer", cid, cid, c.full_name)
        raised += sum(1 for t in txs if t.flags)
    for kid, txs in by_corp.items():
        k = db.get(Corporate, kid)
        _apply(db, txs, k.annual_turnover, "corporate", kid, None, k.legal_name)
        raised += sum(1 for t in txs if t.flags)
    db.flush()
    return {"flagged_transactions": raised}


def _apply(db, txs, profile, etype, eid, customer_id, name):
    for rule, flagged in evaluate(txs, profile).items():
        for t in flagged:
            t.flags = sorted({*t.flags, rule})
        sev, desc = RULES[rule]
        total = sum(t.amount_eur for t in flagged)
        raise_alert(db, source="TXN_MONITORING", entity_type=etype, entity_id=eid, customer_id=customer_id, severity=sev,
                    title=f"{rule.replace('_', ' ').title()}: {name}", description=f"{desc} {len(flagged)} transaction(s), EUR {total:,.0f}.",
                    details={"rule": rule, "txn_refs": [t.txn_ref for t in flagged][:20], "total_eur": round(total, 2)})
