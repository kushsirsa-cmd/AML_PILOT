"""Shared helpers for the investigation / FIU agents."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Corporate, Customer, Transaction

# Jurisdictions often used as transit / transshipment points in sanctions-evasion and TBML typologies (configurable list;
# presence is an indicator to be weighed with other facts - never proof on its own).
TRANSIT_HUBS = {"united arab emirates", "turkey", "cyprus", "hong kong", "kazakhstan", "kyrgyzstan", "armenia", "georgia", "panama", "serbia"}
# Jurisdictions adjacent to active conflict zones, per the institution's TF risk assessment (configurable; indicator only).
CONFLICT_ADJACENT = {"turkey", "lebanon", "jordan", "iraq", "syria", "yemen", "somalia", "afghanistan", "libya", "sudan", "mali", "niger"}
OFFSHORE = {"cyprus", "panama", "cayman islands", "british virgin islands", "seychelles", "belize", "marshall islands"}
TRADE_INDUSTRY_WORDS = ("import", "export", "trading", "commodit", "freight", "logistics", "metals", "shipping", "wholesale", "automotive")
CASH_INTENSIVE_WORDS = ("hospitality", "nightclub", "club", "massage", "spa", "car wash", "restaurant", "bar ", "staffing", "labour", "cleaning", "agricultur")
TRAFFICKING_SPEND_WORDS = ("hotel", "motel", "hostel", "airline", "airways", "bus ", "coach", "booking", "classified", "escort", "taxi", "rental")
CHARITY_WORDS = ("relief", "charity", "aid", "foundation", "humanitarian", "donation", "fund ")
GENERIC_COUNTERPARTY = ("cash deposit", "landlord", "mortgage")


def aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc)


def key(etype: str, eid: int) -> str:
    return f"{etype}:{eid}"


def split_key(k: str) -> tuple[str, int]:
    t, i = k.split(":")
    return t, int(i)


def load_entity(db: Session, etype: str, eid: int):
    obj = db.get(Customer if etype == "customer" else Corporate, eid) if etype in ("customer", "corporate") else None
    if obj is None:
        raise LookupError(f"{etype} {eid} not found")
    return obj


def name_of(obj) -> str:
    return obj.full_name if isinstance(obj, Customer) else obj.legal_name


def ref_of(obj) -> str:
    return obj.customer_ref if isinstance(obj, Customer) else obj.corp_ref


def profile_amount(obj) -> float | None:
    return obj.annual_income if isinstance(obj, Customer) else obj.annual_turnover


def etype_of(obj) -> str:
    return "customer" if isinstance(obj, Customer) else "corporate"


def entity_txs(db: Session, etype: str, eid: int) -> list[Transaction]:
    col = Transaction.customer_id if etype == "customer" else Transaction.corporate_id
    return sorted(db.scalars(select(Transaction).where(col == eid)), key=lambda t: aware(t.ts))


def within(a: datetime, b: datetime, hours: float) -> bool:
    return timedelta(0) <= aware(b) - aware(a) <= timedelta(hours=hours)


def money(x: float) -> str:
    return f"EUR {x:,.0f}"


def level(score: int) -> str:
    return "CRITICAL" if score >= 80 else "HIGH" if score >= 60 else "MEDIUM" if score >= 35 else "LOW"
