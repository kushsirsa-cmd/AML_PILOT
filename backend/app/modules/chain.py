"""Blockchain analytics: exposure tracing, behavioural detectors, risk scoring, graph and trace (Chainalysis-style)."""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AddressLabel, ChainTx

# How dangerous is it to receive from / send to each category? (0 = benign, 1 = worst)
CATEGORY_WEIGHT = {
    "SANCTIONED": 1.0, "RANSOMWARE": 1.0, "TERRORISM_FINANCING": 1.0, "DARKNET": 0.9, "MIXER": 0.8, "SCAM": 0.8,
    "UNREGULATED_EXCHANGE": 0.4, "BRIDGE": 0.25, "GAMBLING": 0.35, "P2P": 0.3, "DEFI": 0.05, "REGULATED_EXCHANGE": 0.0, "UNLABELED": 0.0,
}
CRITICAL_CATEGORIES = {"SANCTIONED", "RANSOMWARE", "TERRORISM_FINANCING"}
STRUCTURING_THRESHOLD_EUR = 10_000
PATTERN_POINTS = {"CRITICAL": 20, "HIGH": 12, "MEDIUM": 7, "LOW": 3}


def aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def level_for(score: int) -> str:
    return "SEVERE" if score >= 70 else "HIGH" if score >= 45 else "MEDIUM" if score >= 20 else "LOW"


class ChainGraph:
    def __init__(self, txs: list[ChainTx], labels: list[AddressLabel]):
        self.labels = {l.address: l for l in labels}
        self.inn: dict[str, list[ChainTx]] = defaultdict(list)
        self.out: dict[str, list[ChainTx]] = defaultdict(list)
        for t in txs:
            self.inn[t.to_address].append(t)
            self.out[t.from_address].append(t)
        self._memo_src: dict = {}
        self._memo_dst: dict = {}

    @classmethod
    def load(cls, db: Session) -> "ChainGraph":
        return cls(list(db.scalars(select(ChainTx))), list(db.scalars(select(AddressLabel))))

    def category(self, addr: str) -> str:
        l = self.labels.get(addr)
        return l.category if l else "UNLABELED"

    # --- exposure (haircut methodology: proportional attribution of value) -----------------------
    def source_mix(self, addr: str, depth: int) -> dict[str, float]:
        if addr in self.labels:
            return {self.labels[addr].category: 1.0}
        ins = self.inn.get(addr)
        if depth <= 0 or not ins:
            return {"UNLABELED": 1.0}
        key = (addr, depth)
        if key in self._memo_src:
            return self._memo_src[key]
        total = sum(t.amount_eur for t in ins) or 1.0
        mix: dict[str, float] = defaultdict(float)
        for t in ins:
            w = t.amount_eur / total
            for c, s in self.source_mix(t.from_address, depth - 1).items():
                mix[c] += w * s
        self._memo_src[key] = dict(mix)
        return self._memo_src[key]

    def dest_mix(self, addr: str, depth: int) -> dict[str, float]:
        if addr in self.labels:
            return {self.labels[addr].category: 1.0}
        outs = self.out.get(addr)
        if depth <= 0 or not outs:
            return {"UNLABELED": 1.0}
        key = (addr, depth)
        if key in self._memo_dst:
            return self._memo_dst[key]
        total = sum(t.amount_eur for t in outs) or 1.0
        mix: dict[str, float] = defaultdict(float)
        for t in outs:
            w = t.amount_eur / total
            for c, s in self.dest_mix(t.to_address, depth - 1).items():
                mix[c] += w * s
        self._memo_dst[key] = dict(mix)
        return self._memo_dst[key]

    def exposure(self, addr: str, depth: int = 3) -> dict:
        ins, outs = self.inn.get(addr, []), self.out.get(addr, [])
        tin, tout = sum(t.amount_eur for t in ins), sum(t.amount_eur for t in outs)
        direct_in: dict[str, float] = defaultdict(float)
        total_in: dict[str, float] = defaultdict(float)
        for t in ins:
            w = t.amount_eur / tin
            direct_in[self.category(t.from_address)] += w
            for c, s in self.source_mix(t.from_address, depth - 1).items():
                total_in[c] += w * s
        direct_out: dict[str, float] = defaultdict(float)
        total_out: dict[str, float] = defaultdict(float)
        for t in outs:
            w = t.amount_eur / tout
            direct_out[self.category(t.to_address)] += w
            for c, s in self.dest_mix(t.to_address, max(depth - 2, 1)).items():
                total_out[c] += w * s
        pct = lambda d: {k: round(v * 100, 1) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if v > 0.0005}
        indirect_in = {c: max(0.0, total_in.get(c, 0) - direct_in.get(c, 0)) for c in total_in if c != "UNLABELED"}
        return {
            "total_received_eur": round(tin, 2), "total_sent_eur": round(tout, 2),
            "sources_direct_pct": pct(direct_in), "sources_total_pct": pct(total_in), "sources_indirect_pct": pct(indirect_in),
            "destinations_direct_pct": pct(direct_out), "destinations_total_pct": pct(total_out),
        }

    # --- behavioural detectors -----------------------------------------------------------------
    def detect_patterns(self, addr: str) -> list[dict]:
        ins = sorted(self.inn.get(addr, []), key=lambda t: aware(t.ts))
        outs = sorted(self.out.get(addr, []), key=lambda t: aware(t.ts))
        allt = sorted(ins + outs, key=lambda t: aware(t.ts))
        found: list[dict] = []
        if not allt:
            return found

        def window(items: list[ChainTx], days: float, pred=lambda t: True):
            """Largest set of items satisfying pred within any sliding window of `days`."""
            best: list[ChainTx] = []
            sel = [t for t in items if pred(t)]
            j = 0
            for i in range(len(sel)):
                while aware(sel[i].ts) - aware(sel[j].ts) > timedelta(days=days):
                    j += 1
                if i - j + 1 > len(best):
                    best = sel[j:i + 1]
            return best

        band = lambda t: 0.8 * STRUCTURING_THRESHOLD_EUR <= t.amount_eur < STRUCTURING_THRESHOLD_EUR
        for label, items in (("incoming", ins), ("outgoing", outs)):
            w = window(items, 14, band)
            if len(w) >= 5:
                found.append(dict(pattern="STRUCTURING", severity="HIGH",
                                  detail=f"{len(w)} {label} transfers of EUR 8,000-9,999 within 14 days (just below the EUR {STRUCTURING_THRESHOLD_EUR:,} threshold), total EUR {sum(t.amount_eur for t in w):,.0f}.",
                                  tx_hashes=[t.tx_hash for t in w]))
                break
        w = window(ins, 14)
        senders = {t.from_address for t in w}
        if len(senders) >= 8:
            found.append(dict(pattern="FAN_IN", severity="MEDIUM",
                              detail=f"Funds aggregated from {len(senders)} distinct addresses within 14 days.", tx_hashes=[t.tx_hash for t in w][:8]))
        w = window(outs, 14)
        receivers = {t.to_address for t in w}
        if len(receivers) >= 8:
            found.append(dict(pattern="FAN_OUT", severity="MEDIUM",
                              detail=f"Funds dispersed to {len(receivers)} distinct addresses within 14 days.", tx_hashes=[t.tx_hash for t in w][:8]))

        tin, tout = sum(t.amount_eur for t in ins), sum(t.amount_eur for t in outs)
        if ins and outs and tin >= 10_000 and tout / tin >= 0.8:
            delays = []
            for o in outs:
                prev = [i for i in ins if aware(i.ts) <= aware(o.ts)]
                if prev:
                    delays.append(((aware(o.ts) - aware(prev[-1].ts)).total_seconds() / 3600, o.amount_eur))
            if delays:
                avg_h = sum(d * v for d, v in delays) / sum(v for _, v in delays)
                if avg_h < 24:
                    found.append(dict(pattern="RAPID_PASS_THROUGH", severity="HIGH",
                                      detail=f"{tout / tin:.0%} of received value (EUR {tin:,.0f}) left again after an average of {avg_h:.1f} hours - wallet acts as a pass-through.",
                                      tx_hashes=[t.tx_hash for t in outs][:8]))

        # peel chain: successive hops each forward >=80% to one address and a small remainder to another
        for o in sorted(outs, key=lambda t: -t.amount_eur):
            cur, length, hashes = o.to_address, 0, [o.tx_hash]
            while cur not in self.labels:
                nxt = self.out.get(cur, [])
                if len(nxt) != 2:
                    break
                big = max(nxt, key=lambda t: t.amount_eur)
                if big.amount_eur / sum(t.amount_eur for t in nxt) < 0.8:
                    break
                length += 1
                hashes.append(big.tx_hash)
                cur = big.to_address
            if length >= 3:
                found.append(dict(pattern="PEEL_CHAIN", severity="HIGH",
                                  detail=f"Outgoing funds were split through a {length}-hop peel chain (each hop forwards ~90% and peels off a small amount), ending at {self.labels[cur].entity_name if cur in self.labels else cur[:12] + '...'}.",
                                  tx_hashes=hashes))
                break

        for t_list, days, limit in ((allt, 7, 20),):
            w = window(t_list, days)
            if len(w) > limit:
                found.append(dict(pattern="HIGH_VELOCITY", severity="LOW", detail=f"{len(w)} transactions in {days} days.", tx_hashes=[t.tx_hash for t in w][:8]))

        first = aware(allt[0].ts)
        volume = tin + tout
        if datetime.now(timezone.utc) - first <= timedelta(days=30) and volume >= 50_000:
            found.append(dict(pattern="NEW_WALLET_LARGE_VOLUME", severity="MEDIUM",
                              detail=f"First activity {(datetime.now(timezone.utc) - first).days} days ago but EUR {volume:,.0f} already moved.", tx_hashes=[allt[0].tx_hash]))
        return found

    # --- tracing -------------------------------------------------------------------------------
    def trace_to_risk(self, addr: str, max_hops: int = 4, min_weight: float = 0.3) -> list[dict]:
        """Shortest backward (source) path from `addr` to each risky category - 'where did the money come from?'"""
        results: dict[str, dict] = {}
        queue = deque([(addr, [])])
        seen = {addr}
        while queue:
            cur, path = queue.popleft()
            if len(path) >= max_hops:
                continue
            for t in sorted(self.inn.get(cur, []), key=lambda x: -x.amount_eur):
                src = t.from_address
                step = dict(from_address=src, to_address=cur, tx_hash=t.tx_hash, amount_eur=t.amount_eur, ts=aware(t.ts).isoformat())
                cat = self.category(src)
                if cat in CATEGORY_WEIGHT and CATEGORY_WEIGHT[cat] >= min_weight and cat not in results:
                    results[cat] = dict(category=cat, entity=self.labels[src].entity_name, hops=len(path) + 1, direction="SOURCE", path=[step] + path)
                if src not in seen and src not in self.labels:
                    seen.add(src)
                    queue.append((src, [step] + path))
        return sorted(results.values(), key=lambda r: (r["hops"], -CATEGORY_WEIGHT[r["category"]]))

    def counterparties(self, addr: str) -> list[dict]:
        agg: dict[str, dict] = {}
        for t in self.inn.get(addr, []):
            c = agg.setdefault(t.from_address, dict(address=t.from_address, sent_eur=0.0, received_eur=0.0, tx_count=0, first=aware(t.ts), last=aware(t.ts)))
            c["received_eur"] += t.amount_eur; c["tx_count"] += 1; c["first"] = min(c["first"], aware(t.ts)); c["last"] = max(c["last"], aware(t.ts))
        for t in self.out.get(addr, []):
            c = agg.setdefault(t.to_address, dict(address=t.to_address, sent_eur=0.0, received_eur=0.0, tx_count=0, first=aware(t.ts), last=aware(t.ts)))
            c["sent_eur"] += t.amount_eur; c["tx_count"] += 1; c["first"] = min(c["first"], aware(t.ts)); c["last"] = max(c["last"], aware(t.ts))
        rows = []
        for a, c in agg.items():
            lab = self.labels.get(a)
            rows.append(dict(address=a, category=lab.category if lab else "UNLABELED", entity=lab.entity_name if lab else None,
                             received_from_eur=round(c["received_eur"], 2), sent_to_eur=round(c["sent_eur"], 2), tx_count=c["tx_count"],
                             first_seen=c["first"].isoformat(), last_seen=c["last"].isoformat()))
        return sorted(rows, key=lambda r: -(r["received_from_eur"] + r["sent_to_eur"]))

    def subgraph(self, addr: str, hops: int = 2, per_node: int = 6) -> dict:
        """Nodes/edges within `hops` of addr, upstream at negative levels and downstream at positive levels."""
        levels = {addr: 0}
        edges: dict[tuple, dict] = {}

        def expand(direction: int):
            frontier = [addr]
            for h in range(1, hops + 1):
                nxt = []
                for node in frontier:
                    if node in self.labels and node != addr:
                        continue
                    pool = self.inn.get(node, []) if direction < 0 else self.out.get(node, [])
                    agg: dict[str, float] = defaultdict(float)
                    for t in pool:
                        agg[t.from_address if direction < 0 else t.to_address] += t.amount_eur
                    for other, _ in sorted(agg.items(), key=lambda kv: -kv[1])[:per_node]:
                        key = (other, node) if direction < 0 else (node, other)
                        vol = [t for t in pool if (t.from_address if direction < 0 else t.to_address) == other]
                        edges[key] = dict(source=key[0], target=key[1], amount_eur=round(sum(t.amount_eur for t in vol), 2), tx_count=len(vol))
                        if other not in levels:
                            levels[other] = direction * h
                            nxt.append(other)
                frontier = nxt

        expand(-1)
        expand(1)
        nodes = []
        for a, lvl in levels.items():
            lab = self.labels.get(a)
            nodes.append(dict(id=a, level=lvl, category=lab.category if lab else "UNLABELED", entity=lab.entity_name if lab else None, focus=(a == addr)))
        return dict(nodes=nodes, edges=list(edges.values()))


def risk_score(exposure: dict, patterns: list[dict]) -> dict:
    """Blockchain risk score 0-100 with an explainable breakdown."""
    comp: dict[str, dict] = {}
    direct = exposure["sources_direct_pct"]
    d_val = sum(direct.get(c, 0) / 100 * w for c, w in CATEGORY_WEIGHT.items())
    comp["direct_source_exposure"] = dict(points=min(50, round(d_val * 100)),
                                          reason="; ".join(f"{v:.1f}% received directly from {k}" for k, v in direct.items() if CATEGORY_WEIGHT.get(k, 0) > 0) or "No direct exposure to risky entities.")
    ind = exposure["sources_indirect_pct"]
    i_val = sum(ind.get(c, 0) / 100 * w for c, w in CATEGORY_WEIGHT.items())
    comp["indirect_source_exposure"] = dict(points=min(25, round(i_val * 80)),
                                            reason="; ".join(f"{v:.1f}% traced indirectly to {k}" for k, v in ind.items() if CATEGORY_WEIGHT.get(k, 0) > 0 and v >= 0.5) or "No indirect exposure within 3 hops.")
    dest = exposure["destinations_total_pct"]
    o_val = sum(dest.get(c, 0) / 100 * w for c, w in CATEGORY_WEIGHT.items())
    comp["destination_exposure"] = dict(points=min(15, round(o_val * 40)),
                                        reason="; ".join(f"{v:.1f}% sent towards {k}" for k, v in dest.items() if CATEGORY_WEIGHT.get(k, 0) > 0 and v >= 0.5) or "No funds sent towards risky entities.")
    b_pts = sum(PATTERN_POINTS[p["severity"]] for p in patterns)
    comp["behaviour"] = dict(points=min(25, b_pts), reason=", ".join(p["pattern"] for p in patterns) or "No suspicious behavioural patterns.")
    score = min(100, sum(c["points"] for c in comp.values()))
    overrides = []
    crit = [c for c in CRITICAL_CATEGORIES if direct.get(c, 0) > 0 or exposure["sources_total_pct"].get(c, 0) >= 5]
    if crit:
        score = max(score, 85)
        overrides.append(f"Exposure to {', '.join(sorted(crit))} forces SEVERE")
    return dict(score=score, level="SEVERE" if crit else level_for(score), components=comp, overrides=overrides)


def screen_address(g: ChainGraph, address: str) -> dict:
    """Full wallet screening result for any address on the (simulated) chain."""
    lab = g.labels.get(address)
    exposure = g.exposure(address)
    patterns = g.detect_patterns(address)
    score = risk_score(exposure, patterns)
    own_category = lab.category if lab else None
    if own_category and CATEGORY_WEIGHT.get(own_category, 0) >= 0.8:  # the address itself is a bad actor
        score["score"] = max(score["score"], 95)
        score["level"] = "SEVERE"
        score["overrides"].append(f"Address is attributed to {lab.entity_name} ({own_category})")
    trace = g.trace_to_risk(address)
    counterparties = g.counterparties(address)
    indicators = [f"{p['pattern']}: {p['detail']}" for p in patterns]
    for t in trace:
        indicators.append(f"{t['category']} source '{t['entity']}' is {t['hops']} hop(s) upstream.")
    return dict(
        address=address, attribution=dict(category=own_category, entity=lab.entity_name if lab else None),
        risk_score=score["score"], risk_level=score["level"], score_components=score["components"], overrides=score["overrides"],
        exposure=exposure, patterns=patterns, risky_traces=trace, top_counterparties=counterparties[:10],
        risk_indicators=indicators, tx_count=len(g.inn.get(address, [])) + len(g.out.get(address, [])),
    )
