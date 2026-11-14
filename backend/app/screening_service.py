"""Fuzzy watch-list matching over the sample sanctions / PEP / adverse-media datasets."""
import json
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from .data.risk_tables import norm_country

DATA_DIR = Path(__file__).parent / "data"
REPORT_THRESHOLD = 65.0  # minimum confidence to create a hit
NAME_FLOOR = 80.0  # minimum fuzzy name score to consider at all

LIST_FILES = {"SANCTIONS": "sanctions.json", "PEP": "peps.json", "ADVERSE_MEDIA": "adverse_media.json"}


def normalise_name(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-zA-Z0-9\s]", " ", s.lower())
    s = re.sub(r"\b(mr|mrs|ms|dr|prof|sir)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def load_lists() -> dict[str, list[dict]]:
    return {k: json.loads((DATA_DIR / f).read_text(encoding="utf-8")) for k, f in LIST_FILES.items()}


def classify(confidence: float) -> str:
    return "STRONG" if confidence >= 90 else "POTENTIAL" if confidence >= 75 else "WEAK"


def _parse_dob(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def score_candidate(name: str, dob: date | None, nationality: str | None, entry: dict) -> dict | None:
    q = normalise_name(name)
    if not q:
        return None
    best_name, best_score = entry["name"], 0.0
    for candidate in [entry["name"], *entry.get("aliases", [])]:
        c = normalise_name(candidate)
        s = max(fuzz.token_sort_ratio(q, c), fuzz.ratio(q, c))
        if s > best_score:
            best_name, best_score = candidate, s
    if best_score < NAME_FLOOR:
        return None

    name_part = best_score * 0.7  # max 70
    entry_dob = _parse_dob(entry.get("dob"))
    dob_part, dob_match = 0.0, "not_available"
    if dob and entry_dob:
        if dob == entry_dob:
            dob_part, dob_match = 20.0, "exact"
        elif dob.year == entry_dob.year:
            dob_part, dob_match = 8.0, "year_only"
        else:
            dob_part, dob_match = -15.0, "mismatch"
    nat_part, nat_match = 0.0, "not_available"
    if nationality and entry.get("nationality"):
        if norm_country(nationality) == norm_country(entry["nationality"]):
            nat_part, nat_match = 10.0, "match"
        else:
            nat_part, nat_match = 0.0, "different"
    confidence = round(max(0.0, min(100.0, name_part + dob_part + nat_part)), 1)
    if confidence < REPORT_THRESHOLD:
        return None
    return {
        "entity_id": entry["id"],
        "matched_name": entry["name"],
        "matched_alias": best_name if best_name != entry["name"] else None,
        "confidence": confidence,
        "strength": classify(confidence),
        "matched_on": {
            "name_similarity": round(best_score, 1),
            "date_of_birth": dob_match,
            "nationality": nat_match,
        },
        "record": {k: v for k, v in entry.items() if k not in ("aliases",)},
    }


def screen(name: str, dob: date | None, nationality: str | None) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for list_type, entries in load_lists().items():
        hits = [h for h in (score_candidate(name, dob, nationality, e) for e in entries) if h]
        out[list_type] = sorted(hits, key=lambda h: -h["confidence"])
    return out
