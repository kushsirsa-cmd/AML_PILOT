"""Network analysis orchestration: link analysis + typology scores of the members."""
from sqlalchemy.orm import Session

from . import links, typology
from .common import split_key


def member_scores(db: Session, idx: links.LinkIndex, keys: list[str]) -> dict[str, int]:
    out = {}
    for k in keys:
        t, i = split_key(k)
        out[k] = typology.detect(db, t, i, idx)["risk_score"]
    return out


def analyze(db: Session, etype: str, eid: int, hops: int = 2) -> dict:
    idx = links.build_index(db)
    comp = idx.component(f"{etype}:{eid}")
    ms = member_scores(db, idx, comp) if len(comp) > 1 else {}
    res = links.analyze_entity(db, etype, eid, hops, idx, ms)
    for n in res["graph"]["nodes"]:
        n["typology_score"] = ms.get(n["key"])
    return res


def clusters(db: Session, min_score: int = 0) -> list[dict]:
    idx = links.build_index(db)
    keys = sorted({k for comp in idx.components(2) for k in comp})
    ms = member_scores(db, idx, keys)
    out = links.clusters(db, min_score, idx, ms)
    for c in out:
        for m in c["members"]:
            m["typology_score"] = ms.get(m["key"])
    return out
