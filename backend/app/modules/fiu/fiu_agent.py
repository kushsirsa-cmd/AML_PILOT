"""FIU AGENT (Financial Intelligence Unit) - alert investigation at network level: entity resolution, link / network analysis,
mule networks, transaction chains, suspicion assessment, SAR recommendation and the intelligence package."""
from __future__ import annotations

from collections import Counter, defaultdict

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Alert, Corporate, Customer, EntityIdentifier, OwnershipNode, Transaction
from .common import aware, entity_txs, etype_of, key, load_entity, money, name_of, now, ref_of, split_key, within
from .links import KIND_LABEL, LinkIndex, build_index
from .network import analyze as net_analyze, member_scores
from .typology import detect


def entity_resolution(db: Session, etype: str, eid: int, idx: LinkIndex) -> list[dict]:
    """Find records that may be the same real-world person / company (fuzzy name + corroborating attributes)."""
    obj = load_entity(db, etype, eid)
    mine_ids = {(r.kind, r.value) for r in db.scalars(select(EntityIdentifier).where(EntityIdentifier.entity_type == etype, EntityIdentifier.entity_id == eid))}
    out = []
    pool: list[tuple[str, int, str, object]] = []
    if etype == "customer":
        pool += [("customer", c.id, c.full_name, c) for c in db.scalars(select(Customer)) if c.id != eid]
        pool += [("corporate", n.corporate_id, n.name, n) for n in db.scalars(select(OwnershipNode).where(OwnershipNode.node_type == "PERSON"))]
    else:
        pool += [("corporate", k.id, k.legal_name, k) for k in db.scalars(select(Corporate)) if k.id != eid]
    nm = name_of(obj).lower()
    for et, oid, other_name, o in pool:
        sim = fuzz.token_sort_ratio(nm, other_name.lower())
        if sim < 80:
            continue
        evidence, conf = [f"name similarity {sim:.0f}%"], sim * 0.5
        if etype == "customer" and getattr(o, "dob", None) == obj.date_of_birth or (etype == "customer" and getattr(o, "date_of_birth", None) == obj.date_of_birth):
            evidence.append("same date of birth"); conf += 25
        if etype == "customer" and getattr(o, "address", None) and o.address == obj.address:
            evidence.append("same address"); conf += 15
        if etype == "corporate" and getattr(o, "registered_address", None) and o.registered_address == obj.registered_address:
            evidence.append("same registered address"); conf += 15
        if etype == "corporate" and getattr(o, "registration_number", None) and o.registration_number == obj.registration_number:
            evidence.append("same registration number"); conf += 30
        other_ids = {(r.kind, r.value) for r in db.scalars(select(EntityIdentifier).where(EntityIdentifier.entity_type == et, EntityIdentifier.entity_id == oid))}
        shared = mine_ids & other_ids
        if shared:
            evidence.append("shared " + ", ".join(sorted({KIND_LABEL.get(k, k) for k, _ in shared}))); conf += 20
        if conf >= 55:
            out.append(dict(entity_type=et, entity_id=oid, name=other_name, confidence=min(99, round(conf)), evidence=evidence,
                            verdict="LIKELY_SAME" if conf >= 85 else "POSSIBLE_SAME", action="Confirm with secondary identifiers before merging or linking records."))
    return sorted(out, key=lambda r: -r["confidence"])[:6]


def flow_chains(db: Session, member_keys: list[str]) -> dict:
    """Aggregate who funds the network members and where the money goes next (funnel / transaction-chain view)."""
    sources: dict[str, dict] = defaultdict(lambda: dict(eur=0.0, count=0, refs=[]))
    dests: dict[tuple, dict] = defaultdict(lambda: dict(eur=0.0, count=0, refs=[], hours=[]))
    legs = []
    member_names = {}
    for k in member_keys:
        et, i = split_key(k)
        obj = load_entity(db, et, i)
        member_names[k] = name_of(obj)
    member_set = set(member_names.values())
    for k in member_keys:
        et, i = split_key(k)
        txs = [t for t in entity_txs(db, et, i) if t.channel != "CARD"]
        monthly = (obj.annual_income / 12) if et == "customer" and obj.annual_income else None
        ins = [t for t in txs if t.direction == "IN" and t.counterparty not in member_set and not (monthly and t.amount_eur >= 0.6 * monthly)]
        outs = [t for t in txs if t.direction == "OUT" and not t.counterparty.lower().startswith("landlord")]
        for t in ins:
            s = sources[t.counterparty]
            s["eur"] += t.amount_eur; s["count"] += 1; s["refs"].append(t.txn_ref)
        for o in outs:
            d = dests[(o.counterparty, o.counterparty_country)]
            d["eur"] += o.amount_eur; d["count"] += 1; d["refs"].append(o.txn_ref)
            prior = [t for t in ins if within(t.ts, o.ts, 72)]
            if prior:
                d["hours"].append(min((aware(o.ts) - aware(t.ts)).total_seconds() / 3600 for t in prior))
            legs.append(dict(member=member_names[k], to=o.counterparty, country=o.counterparty_country, eur=round(o.amount_eur), ref=o.txn_ref))
    in_total = sum(s["eur"] for s in sources.values())
    return dict(
        sources=[dict(name=n, eur=round(v["eur"]), count=v["count"]) for n, v in sorted(sources.items(), key=lambda kv: -kv[1]["eur"])[:12]],
        distinct_sources=len(sources), total_in_eur=round(in_total),
        destinations=[dict(name=n, country=c, eur=round(v["eur"]), count=v["count"], median_hours_after_credit=(sorted(v["hours"])[len(v["hours"]) // 2] if v["hours"] else None),
                           share_of_inflow_pct=round(100 * v["eur"] / in_total) if in_total else None, refs=v["refs"][:12])
                      for (n, c), v in sorted(dests.items(), key=lambda kv: -kv[1]["eur"])[:8]],
        members=list(member_names.values()))


def mule_network(db: Session, comp: list[str], idx: LinkIndex, scores: dict[str, dict]) -> dict | None:
    """A mule network = >=3 linked accounts, most of which show receive-and-forward or small-deposit consolidation."""
    members = [k for k in comp if idx.nodes[k]["type"] == "customer"]
    behav = [k for k in members if any(d["code"] in ("MULE_ACCOUNT", "SMURFING") and d["score"] >= 40 for d in scores[k]["detections"])]
    if len(behav) < 3:
        return None
    chains = flow_chains(db, behav)
    shared = Counter()
    for a in behav:
        for b in behav:
            if a < b and b in idx.adj.get(a, ()):
                for r in idx.edge(a, b)["reasons"]:
                    shared[KIND_LABEL[r["kind"]]] += 1
    controllers = [kind for kind, n in shared.items() if kind in ("device", "bank account", "phone number")]
    return dict(detected=True, members=[idx.nodes[k] for k in behav], size=len(behav), shared_identifiers=dict(shared), chains=chains,
                summary=f"{len(behav)} linked accounts received {money(chains['total_in_eur'])} from {chains['distinct_sources']} sources and forwarded it onward"
                        + (f" - {chains['destinations'][0]['share_of_inflow_pct']}% to {chains['destinations'][0]['name']} ({chains['destinations'][0]['country']})" if chains["destinations"] and chains["destinations"][0]["share_of_inflow_pct"] else "")
                        + (f". Shared {', '.join(controllers)} indicate common control." if controllers else "."))


def suspicion(det: dict, net: dict | None, rbi_conf: int | None, mitigating: list[str], extra: list[str]) -> dict:
    """Suspicion assessment on a 4-step ladder. This is decision support - the suspicion determination belongs to the MLRO."""
    parts = dict(typology=round(0.45 * det["risk_score"]), network=round(0.2 * (net["score"] if net else 0)), screening_sanctions=0, corroboration=0)
    if any(d["code"] == "SANCTIONS_EVASION" and d["score"] >= 50 for d in det["detections"]):
        parts["screening_sanctions"] = 20
    parts["corroboration"] = min(15, 5 * sum(1 for d in det["detections"] if d["score"] >= 40))
    score = min(100, sum(parts.values()) + (5 if not mitigating else 0))
    lvl = "STRONG_SUSPICION" if score >= 75 else "SUSPICION" if score >= 50 else "CONCERN" if score >= 25 else "NO_SUSPICION"
    for_ = [i["text"] for d in det["detections"][:3] for i in d["indicators"][:2]] + extra
    return dict(level=lvl, score=score, components=parts, factors_for=for_[:8], factors_against=mitigating[:5],
                unexplained_activity=bool(det["detections"]) and not mitigating,
                legal_note=("Indicative reporting tests - UK: knowledge, suspicion or reasonable grounds for suspicion of money laundering; Canada: reasonable grounds to suspect "
                            "(lower than reasonable grounds to believe); Singapore: knowledge or reasonable grounds to suspect. The determination is made by the nominated officer / MLRO, not by this agent."))


def sar_recommendation(det: dict, susp: dict, conf: int | None) -> dict:
    top = det["detections"][0] if det["detections"] else None
    if susp["level"] in ("SUSPICION", "STRONG_SUSPICION") and top and top["score"] >= 50:
        rec, why = "FILE", f"Suspicion supported by {top['label'].lower()} (score {top['score']}) and corroborating indicators."
    elif susp["level"] in ("CONCERN", "SUSPICION"):
        rec, why = "REQUEST_INFO", "Concern warrants further information (customer / counterparty / documents) before a reporting decision."
    else:
        rec, why = "DO_NOT_FILE", "Indicators are insufficient. Record the rationale and continue routine monitoring."
    urgent = any(d["mlro_required"] for d in det["detections"])
    return dict(recommendation=rec, rationale=why, urgency="PRIORITY - same-day MLRO review" if urgent else "STANDARD", typologies=det["typologies"],
                formats=["UK SAR (NCA / UKFIU)", "FINTRAC STR", "MAS STR (STRO)", "FIU intelligence package"],
                tipping_off_warning="Do not inform the subject or any third party that a report is being considered or has been made.",
                consent_note="If funds are pending and processing them could involve criminal property, consider requesting consent / a defence from the FIU before proceeding.",
                human_decision_required=True)


def intelligence_package(db: Session, etype: str, eid: int, obj, det: dict, net: dict | None, chains: dict | None, resolution: list[dict], susp: dict, idx: LinkIndex) -> dict:
    k = key(etype, eid)
    txs = entity_txs(db, etype, eid)
    key_txs = sorted(txs, key=lambda t: -t.amount_eur)[:15]
    comp = idx.component(k)
    ids = [dict(kind=r.kind, value=r.value, source=r.source) for r in db.scalars(select(EntityIdentifier).where(EntityIdentifier.entity_type == etype, EntityIdentifier.entity_id == eid))]
    from ...models import Wallet
    wallets = [dict(address=w.address, chain=w.chain, risk=w.risk_level, self_hosted=w.self_hosted) for w in db.scalars(select(Wallet).where((Wallet.customer_id == eid) if etype == "customer" else (Wallet.corporate_id == eid)))]
    return dict(
        package_id=f"INTEL-{ref_of(obj)}-{now():%Y%m%d}", classification="OFFICIAL-SENSITIVE (simulated)", generated_at=now().isoformat(),
        subject=dict(type=etype, ref=ref_of(obj), name=name_of(obj), rating=getattr(obj, "risk_rating", None), country=getattr(obj, "country_of_residence", None) or getattr(obj, "country_of_incorporation", None)),
        associates=[dict(name=idx.nodes[x]["name"], ref=idx.nodes[x]["ref"], type=idx.nodes[x]["type"], rating=idx.nodes[x]["rating"], links=[r["kind"] for r in idx.edge(k, x)["reasons"]] if x in idx.adj.get(k, ()) else []) for x in comp if x != k][:15],
        identifiers=ids, wallets=wallets, resolution_candidates=resolution[:3],
        financial_summary=dict(transactions=len(txs), total_in_eur=round(sum(t.amount_eur for t in txs if t.direction == "IN")), total_out_eur=round(sum(t.amount_eur for t in txs if t.direction == "OUT")),
                               first=aware(txs[0].ts).date().isoformat() if txs else None, last=aware(txs[-1].ts).date().isoformat() if txs else None),
        key_transactions=[dict(ref=t.txn_ref, ts=aware(t.ts).isoformat(), direction=t.direction, eur=round(t.amount_eur, 2), channel=t.channel, counterparty=t.counterparty, country=t.counterparty_country, flags=t.flags) for t in key_txs],
        typologies=[dict(code=d["code"], label=d["label"], score=d["score"], confidence=d["confidence"]) for d in det["detections"]],
        network=dict(size=len(comp), score=net["score"] if net else 0, level=net["level"] if net else "LOW"), flow=chains,
        assessment=dict(level=susp["level"], score=susp["score"]),
        grading=dict(source="Institution's own transaction, KYC and session records (system-generated)", assessment="Rules-engine assessment - requires human validation before dissemination"),
        handling=["Intelligence use only; consider restrictions on onward disclosure", "Do not tip off the subject", "Retain supporting records for the statutory period"])


def investigate(db: Session, etype: str, eid: int, idx: LinkIndex | None = None, rbi_conf: int | None = None, mitigating: list[str] | None = None) -> dict:
    """FIU Investigation Report for one customer / corporate and the network around it."""
    obj = load_entity(db, etype, eid)
    idx = idx or build_index(db)
    k = key(etype, eid)
    comp = idx.component(k) if idx.adj.get(k) else [k]
    ms = {}
    scores = {}
    for m in comp:
        t, i = split_key(m)
        scores[m] = detect(db, t, i, idx)
        ms[m] = scores[m]["risk_score"]
    net_full = net_analyze(db, etype, eid)
    net = net_full["network_risk"] if net_full["linked"] else None
    det = scores[k]
    mule = mule_network(db, comp, idx, scores) if len(comp) >= 3 else None
    chains = flow_chains(db, comp) if len(comp) > 1 else flow_chains(db, [k])
    resolution = entity_resolution(db, etype, eid, idx)
    extra = []
    if mule:
        extra.append(mule["summary"])
    if net_full["hidden_associations"]:
        extra.append(f"{len(net_full['hidden_associations'])} undeclared association(s): " + net_full["hidden_associations"][0]["explanation"])
    mit = mitigating if mitigating is not None else []
    susp = suspicion(det, net, rbi_conf, mit, extra)
    rec = sar_recommendation(det, susp, rbi_conf)
    pkg = intelligence_package(db, etype, eid, obj, det, net, chains, resolution, susp, idx)
    # cluster-level typology roll-up (e.g. structuring, smurfing, layering across the network)
    rollup: dict[str, dict] = {}
    for m, d in scores.items():
        for x in d["detections"]:
            r = rollup.setdefault(x["code"], dict(code=x["code"], label=x["label"], members=[], max_score=0))
            r["members"].append(idx.nodes[m]["name"]); r["max_score"] = max(r["max_score"], x["score"])
    return dict(subject=dict(type=etype, id=eid, ref=ref_of(obj), name=name_of(obj), rating=getattr(obj, "risk_rating", None)), entity_resolution=resolution,
                network=net_full, mule_network=mule, flow_chains=chains, typology=det, network_typologies=sorted(rollup.values(), key=lambda r: -r["max_score"]),
                suspicion=susp, sar_recommendation=rec, intelligence_package=pkg, member_scores=ms)
