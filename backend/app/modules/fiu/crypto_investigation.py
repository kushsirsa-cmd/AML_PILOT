"""CRYPTO INVESTIGATION AGENT - wallet tracing, fund flow, cross-chain (bridge) tracing, mixer identification, clusters and path visualisation
over the simulated ledger. Outputs: Blockchain Investigation Report, Wallet Attribution Report, Exposure Analysis."""
from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ChainTx, Wallet
from ..chain import CATEGORY_WEIGHT, ChainGraph, aware, screen_address
from . import providers
from .common import money, name_of, now

BRIDGE_WINDOW_H = 6
BRIDGE_TOLERANCE = 0.08  # payout within 8% of deposit (fees / slippage)


def forward_trace(g: ChainGraph, addr: str, max_hops: int = 5, min_eur: float = 500) -> dict:
    """Follow value downstream from `addr`; flags the first risky or bridge endpoint on each path."""
    nodes, edges, hits = {addr: dict(id=addr, level=0, category=g.category(addr), entity=g.labels[addr].entity_name if addr in g.labels else None)}, [], []
    q = deque([(addr, 0, [])])
    seen = {addr}
    while q:
        cur, depth, path = q.popleft()
        if depth >= max_hops or (cur in g.labels and cur != addr):
            continue
        for t in sorted(g.out.get(cur, []), key=lambda x: -x.amount_eur)[:8]:
            if t.amount_eur < min_eur:
                continue
            nxt = t.to_address
            step = dict(from_address=cur, to_address=nxt, tx_hash=t.tx_hash, chain=t.chain, asset=t.asset, amount_eur=round(t.amount_eur, 2), ts=aware(t.ts).isoformat())
            edges.append(dict(source=cur, target=nxt, eur=round(t.amount_eur), chain=t.chain))
            cat = g.category(nxt)
            if nxt not in nodes:
                nodes[nxt] = dict(id=nxt, level=depth + 1, category=cat, entity=g.labels[nxt].entity_name if nxt in g.labels else None)
            if CATEGORY_WEIGHT.get(cat, 0) >= 0.25:
                hits.append(dict(category=cat, entity=g.labels[nxt].entity_name, hops=depth + 1, amount_eur=round(t.amount_eur), path=path + [step]))
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, depth + 1, path + [step]))
    return dict(nodes=list(nodes.values()), edges=edges, risky_endpoints=sorted(hits, key=lambda h: (h["hops"], -CATEGORY_WEIGHT.get(h["category"], 0))))


def bridges(g: ChainGraph, addr: str | None = None) -> list[dict]:
    """Pair deposits into BRIDGE-labelled addresses with later payouts on another chain (time + amount heuristic - a lead, not proof)."""
    deps, pays = [], []
    for a, l in g.labels.items():
        if l.category != "BRIDGE":
            continue
        deps += [(a, t) for t in g.inn.get(a, [])]
        pays += [(a, t) for t in g.out.get(a, [])]
    out = []
    for da, d in deps:
        if addr and d.from_address != addr:
            continue
        for pa, p in pays:
            if p.chain == d.chain or pa == da:
                continue
            dh = (aware(p.ts) - aware(d.ts)).total_seconds() / 3600
            if 0 <= dh <= BRIDGE_WINDOW_H and abs(p.amount_eur - d.amount_eur) <= BRIDGE_TOLERANCE * d.amount_eur:
                conf = round(0.9 - 0.4 * (abs(p.amount_eur - d.amount_eur) / d.amount_eur / BRIDGE_TOLERANCE) * 0.5 - 0.05 * dh, 2)
                out.append(dict(source_chain=d.chain, dest_chain=p.chain, deposit=dict(tx=d.tx_hash, from_address=d.from_address, eur=round(d.amount_eur), ts=aware(d.ts).isoformat()),
                                payout=dict(tx=p.tx_hash, to_address=p.to_address, eur=round(p.amount_eur), ts=aware(p.ts).isoformat()), bridge=g.labels[da].entity_name,
                                delay_hours=round(dh, 1), match_confidence=max(0.3, conf), method="time-and-amount pairing (heuristic)"))
    return sorted(out, key=lambda b: -b["match_confidence"])


def clusters_for(g: ChainGraph, addr: str) -> list[dict]:
    """Heuristic clusters around `addr`: unlabelled addresses funded by the same single parent as `addr`, or that fan-in to the same collector."""
    groups = []
    for t in g.inn.get(addr, []):
        parent = t.from_address
        if parent in g.labels:
            continue
        sib = sorted({x.to_address for x in g.out.get(parent, []) if x.to_address != addr and x.to_address not in g.labels})
        if sib:
            groups.append(dict(basis="common funding source", anchor=parent, members=sib[:10], size=len(sib) + 1, confidence="LOW-MEDIUM"))
    for t in g.out.get(addr, []):
        coll = t.to_address
        if coll in g.labels:
            continue
        sib = sorted({x.from_address for x in g.inn.get(coll, []) if x.from_address != addr and x.from_address not in g.labels})
        if sib:
            groups.append(dict(basis="common collector", anchor=coll, members=sib[:10], size=len(sib) + 1, confidence="LOW-MEDIUM"))
    return groups[:6]


def mixer_use(g: ChainGraph, addr: str) -> dict:
    tr = forward_trace(g, addr)
    mix_out = [h for h in tr["risky_endpoints"] if h["category"] == "MIXER"]
    back = [t for t in g.trace_to_risk(addr) if t["category"] == "MIXER"]
    return dict(used=bool(mix_out or back), forward=mix_out[:3], backward=back[:3],
                note="Mixer exposure is a strong indicator but not proof of illicit origin; privacy tools have lawful uses. Judgement rests with the MLRO.")


def investigate_wallet(db: Session, w: Wallet, g: ChainGraph | None = None) -> dict:
    g = g or ChainGraph.load(db)
    scr = screen_address(g, w.address)
    fwd = forward_trace(g, w.address)
    bri = bridges(g, w.address)
    # continue the trace on the destination chain from each bridge payout
    cross = []
    for b in bri:
        onward = forward_trace(g, b["payout"]["to_address"])
        cross.append(dict(bridge=b, onward_endpoints=onward["risky_endpoints"][:4], onward_nodes=len(onward["nodes"])))
    cl = clusters_for(g, w.address)
    mix = mixer_use(g, w.address)
    tri = providers.triangulate(g, w.address)
    owner = None
    if w.customer_id or w.corporate_id:
        from .common import load_entity
        o = load_entity(db, "customer" if w.customer_id else "corporate", w.customer_id or w.corporate_id)
        owner = dict(type="customer" if w.customer_id else "corporate", id=w.customer_id or w.corporate_id, name=name_of(o))
    # unified graph: upstream subgraph + downstream trace
    sub = g.subgraph(w.address, hops=2)
    nodes = {n["id"]: dict(id=n["id"], level=n.get("level", 0), category=n["category"], entity=n["entity"], focus=n["focus"]) for n in sub["nodes"]}
    for n in fwd["nodes"]:
        nodes.setdefault(n["id"], dict(n, focus=n["id"] == w.address))
    for b in bri:
        for a in (b["payout"]["to_address"],):
            nodes.setdefault(a, dict(id=a, level=3, category=g.category(a), entity=None, focus=False))
    edges = {(e["source"], e["target"]): e for e in sub["edges"]}
    for e in fwd["edges"]:
        edges.setdefault((e["source"], e["target"]), e)
    for b in bri:
        edges[(b["deposit"]["from_address"] + "|bridge", b["payout"]["to_address"])] = dict(source=next((a for a, l in g.labels.items() if l.entity_name == b["bridge"] and l.chain == b["source_chain"]), ""), target=b["payout"]["to_address"], eur=b["payout"]["eur"], chain="CROSS-CHAIN", cross_chain=True)
    findings = [f"{scr['risk_level']} blockchain risk ({scr['risk_score']}/100)."] + scr["risk_indicators"][:4]
    if bri:
        findings.append(f"Cross-chain movement via {bri[0]['bridge']}: {money(bri[0]['deposit']['eur'])} on {bri[0]['source_chain']} reappeared on {bri[0]['dest_chain']} after {bri[0]['delay_hours']}h (heuristic match, confidence {bri[0]['match_confidence']}).")
    for c in cross[:1]:
        for h in c["onward_endpoints"][:2]:
            findings.append(f"Onward {h['hops']} hop(s) on destination chain reach {h['entity']} ({h['category']}).")
    if mix["used"]:
        findings.append("Funds interact with a mixer (privacy tool).")
    if tri["disagreement"]:
        findings.append(f"Providers disagree by {tri['spread']} points - review attribution.")
    return dict(
        wallet=dict(id=w.id, address=w.address, chain=w.chain, label=w.label, self_hosted=w.self_hosted, vasp=w.hosted_by_vasp), owner=owner,
        exposure_analysis=dict(score=scr["risk_score"], level=scr["risk_level"], exposure=scr["exposure"], components=scr["score_components"], overrides=scr["overrides"]),
        wallet_attribution=dict(own=scr["attribution"], counterparties=[c for c in scr["top_counterparties"] if c["entity"]][:8], providers=tri["providers"], consensus_score=tri["consensus_score"], disagreement=tri["disagreement"], disclaimer=tri["disclaimer"]),
        fund_flow=dict(upstream=scr["risky_traces"], downstream=fwd["risky_endpoints"][:6], counterparties=scr["top_counterparties"][:8]),
        cross_chain=cross, mixer=mix, clusters=cl, patterns=scr["patterns"],
        path=dict(nodes=list(nodes.values()), edges=list(edges.values())),
        findings=findings, generated_at=now().isoformat(),
        report=dict(title="Blockchain Investigation Report", summary=" ".join(findings[:4]), human_decision_required=True,
                    note="Attribution and bridge pairing are simulated heuristics over a demo ledger; validate with a licensed provider before relying on them."))


def investigate_entity(db: Session, etype: str, eid: int) -> dict:
    ws = list(db.scalars(select(Wallet).where((Wallet.customer_id == eid) if etype == "customer" else (Wallet.corporate_id == eid))))
    g = ChainGraph.load(db)
    reps = [investigate_wallet(db, w, g) for w in ws]
    return dict(wallets=reps, count=len(reps), max_score=max((r["exposure_analysis"]["score"] for r in reps), default=0),
                cross_chain=any(r["cross_chain"] for r in reps), mixer=any(r["mixer"]["used"] for r in reps))
