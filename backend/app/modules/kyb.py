"""KYB agent: corporate onboarding review combining jurisdiction, industry, structure, UBO verification and screening."""
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from ..agents.base import narrate
from ..data.risk_tables import RATING_ORDER, country_risk, industry_risk
from ..models import Analysis, Corporate, OwnershipEdge, OwnershipNode
from ..screening_service import screen
from . import ownership
from .alerts import raise_alert


def load_structure(db: Session, corp: Corporate):
    nodes = list(db.scalars(select(OwnershipNode).where(OwnershipNode.corporate_id == corp.id)))
    edges = list(db.scalars(select(OwnershipEdge).where(OwnershipEdge.corporate_id == corp.id)))
    return nodes, edges


def replace_structure(db: Session, corp: Corporate, nodes: list[dict], edges: list[dict]) -> None:
    """Replace the whole ownership structure. `ROOT` (the corporate itself) is added automatically."""
    keys = {n["key"] for n in nodes}
    if "ROOT" in keys:
        raise ValueError("Node key 'ROOT' is reserved for the corporate itself.")
    if len(keys) != len(nodes):
        raise ValueError("Node keys must be unique.")
    valid = keys | {"ROOT"}
    for e in edges:
        if e["owner"] not in valid or e["owned"] not in valid:
            raise ValueError(f"Edge references unknown node: {e['owner']} -> {e['owned']}")
        if not 0 < float(e["percentage"]) <= 100:
            raise ValueError("Edge percentage must be in (0, 100].")
    db.execute(delete(OwnershipNode).where(OwnershipNode.corporate_id == corp.id))
    db.execute(delete(OwnershipEdge).where(OwnershipEdge.corporate_id == corp.id))
    db.add(OwnershipNode(corporate_id=corp.id, node_key="ROOT", name=corp.legal_name, node_type="ENTITY", country=corp.country_of_incorporation))
    for n in nodes:
        dob = n.get("dob")
        db.add(OwnershipNode(
            corporate_id=corp.id, node_key=n["key"], name=n["name"], node_type=n.get("node_type", "PERSON"), country=n.get("country"),
            dob=date.fromisoformat(dob) if dob else None, role=n.get("role"), id_verified=bool(n.get("id_verified", False)),
            verification_note=n.get("verification_note"), is_listed=bool(n.get("is_listed", False)),
            is_trust=bool(n.get("is_trust", False)), is_nominee=bool(n.get("is_nominee", False)),
        ))
    for e in edges:
        db.add(OwnershipEdge(corporate_id=corp.id, owner_key=e["owner"], owned_key=e["owned"], percentage=float(e["percentage"]),
                             control_type=e.get("control_type", "SHARES")))
    db.flush()


def _screen_party(name: str, dob, country) -> list[dict]:
    out = []
    for list_type, hits in screen(name, dob, country).items():
        for h in hits:
            if h["confidence"] >= 75:
                out.append(dict(party=name, list_type=list_type, matched_name=h["matched_name"], confidence=h["confidence"],
                                strength=h["strength"], detail=h["record"].get("reason") or h["record"].get("position") or h["record"].get("headline")))
    return out


def run(db: Session, corp: Corporate, *, actor: str = "system") -> dict:
    nodes, edges = load_structure(db, corp)
    struct = ownership.analyze(corp, nodes, edges)
    persons = {n.node_key: n for n in nodes}

    # --- screening of every natural person and entity in the structure -----------------------
    hits: list[dict] = []
    for n in nodes:
        label = n.name if n.node_key != "ROOT" else corp.legal_name
        for h in _screen_party(label, n.dob, n.country or corp.country_of_incorporation):
            h["role"] = "COMPANY" if n.node_key == "ROOT" else ("UBO/OWNER" if n.node_type == "PERSON" else "INTERMEDIATE ENTITY")
            hits.append(h)
    hit_by_party: dict[str, list[dict]] = {}
    for h in hits:
        hit_by_party.setdefault(h["party"], []).append(h)

    # --- UBO verification -------------------------------------------------------------------
    for u in struct["ubos"]:
        ph = hit_by_party.get(u["name"], [])
        if any(h["list_type"] == "SANCTIONS" and h["confidence"] >= 90 for h in ph):
            u["status"] = "SANCTIONS_MATCH"
        elif any(h["list_type"] == "SANCTIONS" for h in ph):
            u["status"] = "POTENTIAL_SANCTIONS_MATCH"
        elif any(h["list_type"] == "PEP" for h in ph):
            u["status"] = "PEP"
        elif any(h["list_type"] == "ADVERSE_MEDIA" for h in ph):
            u["status"] = "ADVERSE_MEDIA"
        elif not u["id_verified"]:
            u["status"] = "UNVERIFIED"
        else:
            u["status"] = "VERIFIED"
        u["screening"] = ph
    statuses = {u["status"] for u in struct["ubos"]}
    if not struct["ubos"]:
        ubo_status = "NOT_IDENTIFIED"
    elif statuses & {"SANCTIONS_MATCH", "POTENTIAL_SANCTIONS_MATCH"}:
        ubo_status = "SANCTIONS_ALERT"
    elif "UNVERIFIED" in statuses or struct["metrics"]["unaccounted_pct"] > 0.5:
        ubo_status = "INCOMPLETE"
    else:
        ubo_status = "VERIFIED"
    verified_pct = sum(u["effective_pct"] for u in struct["ubos"] if u["status"] in ("VERIFIED", "PEP", "ADVERSE_MEDIA"))

    # --- scoring ----------------------------------------------------------------------------
    inc = country_risk(corp.country_of_incorporation)
    op_risks = [country_risk(c.strip()) for c in (corp.operating_countries or "").split(",") if c.strip()]
    op_max = max(op_risks, key=lambda r: r["score"], default=None)
    comp: dict[str, dict] = {}
    comp["incorporation_jurisdiction"] = dict(points=min(25, inc["score"]), reason=inc["reason"])
    comp["operating_jurisdictions"] = dict(points=min(15, round(op_max["score"] * 0.6)) if op_max else 0,
                                           reason=op_max["reason"] if op_max and op_max["score"] else "No elevated-risk operating countries.")
    ind = industry_risk(corp.industry)
    comp["industry"] = dict(points=min(20, ind["score"]), reason=ind["reason"])
    comp["ownership_structure"] = dict(points=struct["structure_points"],
                                       reason=", ".join(f["code"] for f in struct["red_flags"]) or "Simple, transparent structure.")
    ubo_pts, ubo_reasons = 0, []
    if not struct["ubos"]:
        ubo_pts += 25; ubo_reasons.append("no UBO identified")
    unver = [u for u in struct["ubos"] if u["status"] == "UNVERIFIED"]
    if unver:
        ubo_pts += min(20, 10 * len(unver)); ubo_reasons.append(f"{len(unver)} UBO(s) not verified")
    if any(u["status"] == "PEP" for u in struct["ubos"]):
        ubo_pts += 15; ubo_reasons.append("PEP UBO")
    if any(u["status"] == "ADVERSE_MEDIA" for u in struct["ubos"]):
        ubo_pts += 10; ubo_reasons.append("adverse media on UBO")
    if any(u["status"] in ("SANCTIONS_MATCH", "POTENTIAL_SANCTIONS_MATCH") for u in struct["ubos"]):
        ubo_pts += 40; ubo_reasons.append("sanctions match on UBO")
    comp["ubo_verification"] = dict(points=min(40, ubo_pts), reason="; ".join(ubo_reasons) or "All UBOs identified and verified.")
    ent_sanc = [h for h in hits if h["list_type"] == "SANCTIONS" and h["role"] != "UBO/OWNER"]
    comp["entity_screening"] = dict(points=40 if any(h["confidence"] >= 90 for h in ent_sanc) else 20 if ent_sanc else 0,
                                    reason="; ".join(f"{h['party']} ~ {h['matched_name']} ({h['confidence']:.0f}%)" for h in ent_sanc) or "No sanctions hits on company or intermediate entities.")
    shell = []
    if corp.incorporation_date and (date.today() - corp.incorporation_date).days < 365:
        shell.append("incorporated < 12 months ago")
    if (corp.employees or 0) == 0:
        shell.append("no employees")
    if corp.registered_address and corp.registered_address.lower().startswith(("po box", "c/o")):
        shell.append("registered address is a PO box / c/o")
    missing = [f for f in ("registration_number", "registered_address", "operating_countries", "annual_turnover", "expected_activity", "incorporation_date")
               if not getattr(corp, f)]
    comp["shell_and_profile"] = dict(points=min(15, 4 * len(shell) + 2 * len(missing)),
                                     reason=("shell indicators: " + ", ".join(shell) if shell else "") + (("; " if shell and missing else "") + "missing: " + ", ".join(missing) if missing else "") or "Profile complete, no shell indicators.")

    score = min(100, sum(c["points"] for c in comp.values()))
    rating = "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW"
    overrides = []

    def floor(level: str, why: str):
        nonlocal rating
        if RATING_ORDER.index(level) > RATING_ORDER.index(rating):
            rating = level
        overrides.append(f"{why} -> minimum rating {level}")

    if inc["level"] == "PROHIBITED":
        floor("PROHIBITED", "Incorporated in a prohibited jurisdiction")
    if any(h["list_type"] == "SANCTIONS" and h["confidence"] >= 90 for h in hits):
        floor("PROHIBITED", "Strong sanctions match on company, intermediate entity or UBO")
    if any(u["status"] == "PEP" for u in struct["ubos"]):
        floor("HIGH", "PEP UBO")
    if ubo_status in ("NOT_IDENTIFIED", "INCOMPLETE") and rating == "LOW":
        floor("MEDIUM", f"UBO status {ubo_status}")
    if ubo_status == "SANCTIONS_ALERT" and rating in ("LOW", "MEDIUM"):
        floor("HIGH", "Potential sanctions match on UBO")

    if rating == "PROHIBITED":
        rec = "REJECT_AND_ESCALATE_MLRO"
    elif ubo_status in ("NOT_IDENTIFIED", "INCOMPLETE"):
        rec = "REQUEST_UBO_DOCUMENTATION"
    elif rating == "HIGH":
        rec = "EDD_AND_SENIOR_APPROVAL"
    elif rating == "MEDIUM":
        rec = "APPROVE_WITH_ENHANCED_MONITORING"
    else:
        rec = "APPROVE"

    requests = []
    for u in unver:
        requests.append(f"Verify identity of UBO {u['name']} ({u['effective_pct']:g}%): certified passport/ID and proof of address.")
    if struct["metrics"]["unaccounted_pct"] > 0.5:
        requests.append(f"Identify owners of the remaining {struct['metrics']['unaccounted_pct']:g}% of the company (share register / shareholder agreement).")
    for f in struct["red_flags"]:
        if f["code"] == "TRUST_IN_CHAIN":
            requests.append("Obtain trust deed and identify settlor, trustees and beneficiaries.")
        if f["code"] == "NOMINEES":
            requests.append("Obtain nominee agreements and the identity of the nominators.")
        if f["code"] == "CIRCULAR_OWNERSHIP":
            requests.append("Obtain legal explanation and chart for the circular shareholding.")
    if ind["level"] == "HIGH":
        requests.append("Obtain licence / regulatory authorisation for the regulated activity.")

    reasoning = [f"{k.replace('_', ' ').title()}: +{v['points']} - {v['reason']}" for k, v in comp.items() if v["points"]]
    reasoning.append(f"Total {score}/100 (LOW <25, MEDIUM 25-49, HIGH >=50).")
    reasoning += [f"Override: {o}" for o in overrides]
    fallback = (f"{corp.legal_name} ({corp.country_of_incorporation}) rates {rating} (score {score}). UBO status: {ubo_status.replace('_', ' ').lower()}; "
                f"structure risk {struct['structure_risk'].lower()} with {struct['metrics']['layers']} layer(s). Recommendation: {rec.replace('_', ' ').lower()}.")
    narrative, engine = narrate(
        "Write a KYB review summary for the analyst: structure, who the UBOs are, verification gaps and the recommendation.",
        dict(company=corp.legal_name, rating=rating, score=score, ubo_status=ubo_status, ubos=[{k: u[k] for k in ("name", "effective_pct", "status")} for u in struct["ubos"]],
             red_flags=[f["detail"] for f in struct["red_flags"]], hits=hits[:6], recommendation=rec), fallback)

    out = dict(
        risk_rating=rating, risk_score=score, components=comp, overrides=overrides, reasoning=reasoning,
        ubo_status=ubo_status, ubo_verified_ownership_pct=round(verified_pct, 1), ubo_verification=struct["ubos"],
        other_persons=struct["other_persons"], fallback_senior_managing_officials=struct["fallback_senior_managing_officials"],
        structure=dict(risk=struct["structure_risk"], metrics=struct["metrics"], red_flags=struct["red_flags"]), ownership_tree=struct["tree"],
        screening_hits=hits, recommendation=rec, information_requests=requests, narrative=narrative, engine=engine,
    )
    previous = corp.risk_rating
    corp.risk_rating, corp.risk_score = rating, score
    db.add(Analysis(entity_type="corporate", entity_id=corp.id, kind="kyb", engine=engine, output=out))
    audit.log(db, actor=f"KYB Agent ({engine})", actor_type=audit.AI, action="KYB_REVIEW", entity_type="corporate", entity_id=corp.id,
              details=dict(requested_by=actor, rating=rating, score=score, ubo_status=ubo_status, recommendation=rec))
    if previous != rating:
        audit.log(db, actor=f"KYB Agent ({engine})", actor_type=audit.AI, action="CORPORATE_RATING_CHANGED", entity_type="corporate",
                  entity_id=corp.id, details=dict(**{"from": previous, "to": rating}, score=score))
    if rating in ("HIGH", "PROHIBITED") or ubo_status == "SANCTIONS_ALERT":
        raise_alert(db, source="KYB", entity_type="corporate", entity_id=corp.id, severity="CRITICAL" if rating == "PROHIBITED" else "HIGH",
                    title=f"KYB: {corp.legal_name} rated {rating}", description="; ".join(reasoning[:4]),
                    details=dict(ubo_status=ubo_status, recommendation=rec))
    db.flush()
    return out
