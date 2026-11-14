"""Shared helpers for agents."""
import json
import re
from datetime import date

from .. import llm
from ..models import Customer


def customer_facts(c: Customer) -> dict:
    return {
        "customer_ref": c.customer_ref,
        "name": c.full_name,
        "date_of_birth": c.date_of_birth.isoformat() if c.date_of_birth else None,
        "nationality": c.nationality,
        "country_of_residence": c.country_of_residence,
        "occupation": c.occupation,
        "industry": c.industry,
        "annual_income_eur": c.annual_income,
        "product": c.product,
        "channel": c.channel,
        "pep_declared": c.pep_declared,
    }


def narrate(task: str, facts: dict, fallback: str, max_tokens: int = 450) -> tuple[str, str]:
    """Ask Claude to write a short narrative from structured facts; fall back to the rule-based text."""
    prompt = (
        f"{task}\n\n<facts>\n{json.dumps(facts, default=str, indent=1)}\n</facts>\n\n"
        "Write 3-6 sentences of plain prose (no headings, no bullet points)."
    )
    text = llm.ask(prompt, max_tokens=max_tokens)
    return (text, "rules+claude") if text else (fallback, "rules")


def age_on(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


_NUM = re.compile(r"(\d[\d,\.]*)\s*(million|thousand|k|m)?\b", re.IGNORECASE)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}


def _annual_factor(before: str, after: str) -> int:
    """Infer the period of a figure from the words around it (monthly -> x12, weekly -> x52, annual -> x1)."""
    if "month" in after or "/m" in after or "p.m" in after:
        return 12
    if "week" in after:
        return 52
    if "year" in after or "annual" in after or "p.a" in after:
        return 1
    if "monthly" in before or "per month" in before:
        return 12
    return 1


def annualised_expected_activity(text: str | None) -> float | None:
    """Sum every monetary figure in the expected-activity text, annualised by the period named next to it."""
    text = text or ""
    low = text.lower()
    total, found = 0.0, False
    for m in _NUM.finditer(low):
        raw, suffix = m.group(1), (m.group(2) or "")
        cleaned = raw.replace(",", "").rstrip(".")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        if not suffix and "," not in raw and 1900 <= value <= 2100:
            continue  # looks like a year
        value *= _MULT.get(suffix, 1)
        if value < 100:
            continue  # percentages, counts, etc.
        before, after = low[max(0, m.start() - 30): m.start()], low[m.end(): m.end() + 14]
        total += value * _annual_factor(before, after)
        found = True
    return total if found else None
