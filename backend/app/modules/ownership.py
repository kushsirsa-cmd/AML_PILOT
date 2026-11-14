"""Corporate ownership structure analysis and ultimate-beneficial-owner (UBO) derivation."""
from collections import defaultdict

from ..data.risk_tables import norm_country
from ..models import Corporate, OwnershipEdge, OwnershipNode

UBO_THRESHOLD_PCT = 25.0
SECRECY_JURISDICTIONS = {
    "british virgin islands", "seychelles", "panama", "cayman islands", "belize", "marshall islands", "vanuatu",
    "samoa", "bahamas", "jersey", "guernsey", "liechtenstein", "nevis", "anguilla", "bermuda",
}
CONTROL_ROLES = ("DIRECTOR", "CEO", "MANAGING_DIRECTOR", "MANAGER")


def analyze(corp: Corporate, nodes: list[OwnershipNode], edges: list[OwnershipEdge], threshold: float = UBO_THRESHOLD_PCT) -> dict:
    by_key = {n.node_key: n for n in nodes}
    owners_of: dict[str, list[OwnershipEdge]] = defaultdict(list)
    for e in edges:
        owners_of[e.owned_key].append(e)

    effective: dict[str, float] = defaultdict(float)
    paths: dict[str, list[str]] = defaultdict(list)
    control_basis: dict[str, set] = defaultdict(set)
    unaccounted = 0.0
    circular: list[str] = []
    listed_exempt: list[str] = []
    max_depth = 0
    visited_entities: set[str] = set()

    def walk(key: str, acc: float, trail: list[str], depth: int):
        nonlocal unaccounted, max_depth
        in_edges = owners_of.get(key, [])
        total_in = sum(e.percentage for e in in_edges if e.control_type == "SHARES")
        if total_in < 99.9:
            unaccounted += acc * (100 - total_in) / 100
        for e in in_edges:
            owner = by_key.get(e.owner_key)
            if owner is None:
                continue
            if owner.node_key in trail:
                circular.append(" -> ".join([by_key[k].name for k in trail[trail.index(owner.node_key):]] + [owner.name]))
                continue
            share = acc * e.percentage / 100
            label = f"{owner.name} ({e.percentage:g}%{'' if e.control_type == 'SHARES' else ' ' + e.control_type.lower()})"
            max_depth = max(max_depth, depth + 1)
            if owner.node_type == "PERSON":
                effective[owner.node_key] += share * 100
                paths[owner.node_key].append(" <- ".join([by_key[trail[0]].name] + [by_key[k].name for k in trail[1:]] + [label]))
                if e.control_type != "SHARES":
                    control_basis[owner.node_key].add(e.control_type)
            else:
                visited_entities.add(owner.node_key)
                if owner.is_listed:
                    listed_exempt.append(owner.name)
                    continue
                walk(owner.node_key, share, trail + [owner.node_key], depth + 1)

    walk("ROOT", 1.0, ["ROOT"], 0)

    persons = {n.node_key: n for n in nodes if n.node_type == "PERSON"}
    ubos, others = [], []
    for k, n in persons.items():
        eff = round(effective.get(k, 0.0), 2)
        basis = []
        if eff >= threshold:
            basis.append(f"{eff:g}% effective ownership (>= {threshold:g}%)")
        if control_basis.get(k):
            basis.append("control via " + ", ".join(sorted(x.lower() for x in control_basis[k])))
        row = dict(key=k, name=n.name, country=n.country, dob=n.dob.isoformat() if n.dob else None, role=n.role,
                   effective_pct=eff, basis=basis, paths=paths.get(k, []), id_verified=n.id_verified,
                   verification_note=n.verification_note)
        (ubos if basis else others).append(row)
    ubos.sort(key=lambda r: -r["effective_pct"])

    fallback = []
    if not ubos:
        fallback = [dict(key=n.node_key, name=n.name, role=n.role, id_verified=n.id_verified)
                    for n in persons.values() if (n.role or "").upper() in CONTROL_ROLES]

    entities = [n for n in nodes if n.node_type == "ENTITY" and n.node_key != "ROOT"]
    countries = {norm_country(n.country): n.country for n in nodes if n.country}
    countries.setdefault(norm_country(corp.country_of_incorporation), corp.country_of_incorporation)
    secrecy = sorted({v for k, v in countries.items() if k in SECRECY_JURISDICTIONS})
    trusts = [n.name for n in nodes if n.is_trust]
    nominees = [n.name for n in nodes if n.is_nominee]

    flags: list[dict] = []
    pts = 0

    def flag(code: str, severity: str, detail: str, points: int):
        nonlocal pts
        flags.append(dict(code=code, severity=severity, detail=detail, points=points))
        pts += points

    if max_depth > 2:
        flag("COMPLEX_LAYERING", "MEDIUM", f"{max_depth} ownership layers between the company and its ultimate owners.", min(10, 4 * (max_depth - 2)))
    if secrecy:
        flag("SECRECY_JURISDICTION", "HIGH", "Entities / owners in secrecy jurisdictions: " + ", ".join(secrecy) + ".", min(16, 8 * len(secrecy)))
    if len(countries) >= 4:
        flag("MANY_JURISDICTIONS", "MEDIUM", f"Structure spans {len(countries)} jurisdictions without evident commercial rationale.", 5)
    if trusts:
        flag("TRUST_IN_CHAIN", "MEDIUM", "Trust(s) in the ownership chain: " + ", ".join(trusts) + " - settlor/beneficiaries must be identified.", 6)
    if nominees or corp.nominee_directors:
        flag("NOMINEES", "HIGH", "Nominee shareholders / directors used" + (": " + ", ".join(nominees) if nominees else "") + ".", 8)
    if corp.has_bearer_shares:
        flag("BEARER_SHARES", "HIGH", "Bearer shares issued - ownership can pass without registration.", 10)
    if circular:
        flag("CIRCULAR_OWNERSHIP", "HIGH", "Circular ownership: " + "; ".join(sorted(set(circular))) + ".", 15)
    if unaccounted > 0.005:
        flag("UNACCOUNTED_OWNERSHIP", "HIGH" if unaccounted > 0.1 else "MEDIUM",
             f"{unaccounted * 100:.1f}% of the company cannot be traced to a named owner.", min(15, round(unaccounted * 100 * 0.5)))
    if not ubos:
        flag("NO_UBO_IDENTIFIED", "HIGH", f"No natural person holds >= {threshold:g}% or exercises identified control.", 15)

    def tree(key: str, pct: float | None, trail: tuple) -> dict:
        n = by_key[key]
        node = dict(name=n.name, type=n.node_type, country=n.country, pct=pct, trust=n.is_trust, nominee=n.is_nominee,
                    listed=n.is_listed, verified=n.id_verified, children=[])
        if key in trail or (n.is_listed and key != "ROOT"):
            return node
        for e in owners_of.get(key, []):
            if e.owner_key in by_key:
                node["children"].append(tree(e.owner_key, e.percentage, trail + (key,)))
        return node

    return dict(
        ubo_threshold_pct=threshold, ubos=ubos, other_persons=others, fallback_senior_managing_officials=fallback,
        metrics=dict(layers=max_depth, entities=len(entities), jurisdictions=sorted(countries.values()), secrecy_jurisdictions=secrecy,
                     trusts=len(trusts), nominees=len(nominees), unaccounted_pct=round(unaccounted * 100, 1),
                     circular=sorted(set(circular)), listed_exempt=listed_exempt),
        red_flags=flags, structure_points=min(40, pts),
        structure_risk="HIGH" if pts >= 25 else "MEDIUM" if pts >= 10 else "LOW",
        tree=tree("ROOT", None, ()),
    )
