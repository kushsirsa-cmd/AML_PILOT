"""ENTITY LINK ANALYSIS AGENT - shared phone / email / IP / device / wallet / bank account, shared directors and UBOs.

Deterministic and explainable: every edge lists exactly which shared attribute created it and how much it weighs.
Outputs: relationship graph, network (cluster) risk score, hidden-association detection.
"""
from __future__ import annotations

from collections import defaultdict, deque
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import AddressLabel, Alert, ChainTx, Corporate, Customer, EntityIdentifier, OwnershipNode, ScreeningHit, Transaction, Wallet
from .common import key, name_of, ref_of, split_key

# How strongly each kind of shared attribute suggests a real-world connection (0-100 scale, summed per pair, capped at 100).
KIND_WEIGHT = {"BANK_ACCOUNT": 30, "WALLET": 28, "UBO": 30, "DIRECTOR": 24, "DEVICE": 22, "PHONE": 16, "EMAIL": 14, "ADDRESS": 10, "IP": 8, "CASHOUT": 8}
KIND_LABEL = {"BANK_ACCOUNT": "bank account", "WALLET": "wallet", "UBO": "UBO / shareholder", "DIRECTOR": "director", "DEVICE": "device",
              "PHONE": "phone number", "EMAIL": "email address", "ADDRESS": "address", "IP": "IP address", "CASHOUT": "cash-out wallet"}
DECLARED_KINDS = {"UBO", "DIRECTOR"}  # relationships the institution already knows about from KYB / ownership data
LINK_THRESHOLD = 14   # minimum combined edge weight to treat two entities as connected
MAX_GROUP = {"IP": 6, "ADDRESS": 8}  # a value shared by more entities than this is a household / carrier / mass-registration address, not a signal
DEFAULT_MAX_GROUP = 12
RISKY_RATINGS = {"HIGH", "PROHIBITED"}


class LinkIndex:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[frozenset, list[dict]] = defaultdict(list)
        self.adj: dict[str, set[str]] = defaultdict(set)
        self.sanctioned: set[str] = set()

    # ------------------------------------------------------------------ construction
    def add_edge(self, a: str, b: str, kind: str, detail: str):
        if a == b or a not in self.nodes or b not in self.nodes:
            return
        pair = frozenset((a, b))
        if any(r["kind"] == kind and r["detail"] == detail for r in self.edges[pair]):
            return
        self.edges[pair].append(dict(kind=kind, detail=detail, weight=KIND_WEIGHT[kind]))

    def finalize(self):
        for pair, reasons in self.edges.items():
            if self.strength(pair) >= LINK_THRESHOLD:
                a, b = tuple(pair)
                self.adj[a].add(b)
                self.adj[b].add(a)

    def strength(self, pair) -> int:
        per_kind: dict[str, int] = {}
        for r in self.edges[pair]:
            per_kind[r["kind"]] = max(per_kind.get(r["kind"], 0), r["weight"])
        return min(100, sum(per_kind.values()))

    # ------------------------------------------------------------------ queries
    def edge(self, a: str, b: str) -> dict:
        pair = frozenset((a, b))
        return dict(source=a, target=b, strength=self.strength(pair), reasons=self.edges[pair],
                    declared=all(r["kind"] in DECLARED_KINDS for r in self.edges[pair]))

    def component(self, start: str) -> list[str]:
        seen, q = {start}, deque([start])
        while q:
            cur = q.popleft()
            for nb in self.adj.get(cur, ()):
                if nb not in seen:
                    seen.add(nb)
                    q.append(nb)
        return sorted(seen)

    def components(self, min_size: int = 2) -> list[list[str]]:
        seen: set[str] = set()
        out = []
        for k in sorted(self.adj):
            if k in seen:
                continue
            comp = self.component(k)
            seen.update(comp)
            if len(comp) >= min_size:
                out.append(comp)
        return out

    def neighborhood(self, start: str, hops: int = 2) -> list[str]:
        seen, frontier = {start}, [start]
        for _ in range(hops):
            nxt = []
            for k in frontier:
                for nb in self.adj.get(k, ()):
                    if nb not in seen:
                        seen.add(nb)
                        nxt.append(nb)
            frontier = nxt
        return sorted(seen)

    def graph(self, keys: list[str]) -> dict:
        ks = set(keys)
        nodes = [self.nodes[k] for k in keys]
        edges = [self.edge(*tuple(p)) for p in self.edges if p <= ks and self.strength(p) >= LINK_THRESHOLD]
        return dict(nodes=nodes, edges=sorted(edges, key=lambda e: -e["strength"]))

    # ------------------------------------------------------------------ scoring
    def score(self, keys: list[str], member_scores: dict[str, int] | None = None) -> dict:
        """Network risk score 0-100 with the arithmetic shown. member_scores = typology risk score per member (optional)."""
        member_scores = member_scores or {}
        members = [self.nodes[k] for k in keys]
        ks = set(keys)
        pairs = [p for p in self.edges if p <= ks and self.strength(p) >= LINK_THRESHOLD]
        parts: dict[str, dict] = {}
        n = len(members)
        parts["size"] = dict(points=min(20, 5 * (n - 1)), why=f"{n} connected entities")
        avg = sum(self.strength(p) for p in pairs) / len(pairs) if pairs else 0
        parts["link_strength"] = dict(points=round(avg / 100 * 20), why=f"average link strength {avg:.0f}/100 across {len(pairs)} link(s)")
        risky = [m for m in members if m["rating"] in RISKY_RATINGS]
        parts["member_risk"] = dict(points=min(20, round(20 * len(risky) / n)), why=f"{len(risky)} of {n} member(s) rated HIGH / PROHIBITED")
        sanc = [m for m in members if m["key"] in self.sanctioned]
        parts["sanctions_pep"] = dict(points=20 if sanc else 0, why=("sanctions / PEP screening match inside the network: " + ", ".join(m["name"] for m in sanc[:3])) if sanc else "no screening matches inside the network")
        flagged = [m for m in members if m["alerts"] > 0 or m["flagged_txns"] > 0 or member_scores.get(m["key"], 0) >= 40]
        parts["behaviour"] = dict(points=min(25, round(25 * len(flagged) / n)), why=f"{len(flagged)} of {n} member(s) have open alerts, flagged transactions or a typology score >= 40")
        hidden = self.hidden_associations(keys)
        parts["hidden"] = dict(points=min(10, 5 * len(hidden)), why=f"{len(hidden)} undeclared association(s) between entities with no disclosed relationship")
        total = min(100, sum(p["points"] for p in parts.values()))
        label = "CRITICAL" if total >= 75 else "HIGH" if total >= 55 else "MEDIUM" if total >= 35 else "LOW"
        return dict(score=total, level=label, components=parts)

    def hidden_associations(self, keys: list[str]) -> list[dict]:
        """Undeclared links (shared contact / technical identifiers) between entities that have no disclosed relationship."""
        ks = set(keys)
        out = []
        for p in self.edges:
            if not p <= ks or self.strength(p) < LINK_THRESHOLD:
                continue
            e = self.edge(*tuple(p))
            if e["declared"]:
                continue
            a, b = self.nodes[e["source"]], self.nodes[e["target"]]
            declared_between = any(r["kind"] in DECLARED_KINDS for r in self.edges[p])
            if declared_between:
                continue
            if {r["kind"] for r in e["reasons"]} <= {"ADDRESS", "IP"}:
                continue  # same address + same broadband = most likely a household, not a hidden association
            kinds = ", ".join(sorted({KIND_LABEL[r["kind"]] for r in e["reasons"]}))
            mismatch = (a["rating"] in RISKY_RATINGS) != (b["rating"] in RISKY_RATINGS)
            out.append(dict(a=a["key"], b=b["key"], a_name=a["name"], b_name=b["name"], shared=kinds, strength=e["strength"], rating_mismatch=mismatch,
                            explanation=f"{a['name']} ({a['rating'] or 'unrated'}) and {b['name']} ({b['rating'] or 'unrated'}) share {kinds}; no relationship is disclosed in KYC/KYB data."))
        return sorted(out, key=lambda h: (-int(h["rating_mismatch"]), -h["strength"]))


def build_index(db: Session) -> LinkIndex:
    idx = LinkIndex()
    flagged: dict[str, int] = defaultdict(int)
    for t in db.scalars(select(Transaction)):
        if t.flags:
            flagged[key("customer", t.customer_id) if t.customer_id else key("corporate", t.corporate_id)] += 1
    open_alerts: dict[str, int] = defaultdict(int)
    for a in db.scalars(select(Alert).where(Alert.status != "CLOSED")):
        if a.entity_type in ("customer", "corporate"):
            open_alerts[key(a.entity_type, a.entity_id)] += 1
        elif a.customer_id:
            open_alerts[key("customer", a.customer_id)] += 1
    for c in db.scalars(select(Customer)):
        k = key("customer", c.id)
        idx.nodes[k] = dict(key=k, type="customer", id=c.id, name=c.full_name, ref=c.customer_ref, rating=c.risk_rating, status=c.status,
                            country=c.country_of_residence, alerts=open_alerts.get(k, 0), flagged_txns=flagged.get(k, 0))
    for c in db.scalars(select(Corporate)):
        k = key("corporate", c.id)
        idx.nodes[k] = dict(key=k, type="corporate", id=c.id, name=c.legal_name, ref=c.corp_ref, rating=c.risk_rating, status=c.status,
                            country=c.country_of_incorporation, alerts=open_alerts.get(k, 0), flagged_txns=flagged.get(k, 0))
    for h in db.scalars(select(ScreeningHit).where(ScreeningHit.disposition != "FALSE_POSITIVE", ScreeningHit.confidence >= 85)):
        if h.list_type in ("SANCTIONS", "PEP"):
            idx.sanctioned.add(key("customer", h.customer_id))

    # --- shared identifiers (phone / email / IP / device / wallet / bank account)
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in db.scalars(select(EntityIdentifier)):
        groups[(r.kind, r.value.strip().lower())].add(key(r.entity_type, r.entity_id))
    # wallets registered to an entity are WALLET identifiers too
    for w in db.scalars(select(Wallet)):
        owner = key("customer", w.customer_id) if w.customer_id else key("corporate", w.corporate_id) if w.corporate_id else None
        if owner:
            groups[("WALLET", w.address.lower())].add(owner)
    for (kind, value), members in groups.items():
        if len(members) < 2 or len(members) > MAX_GROUP.get(kind, DEFAULT_MAX_GROUP):
            continue
        for a, b in combinations(sorted(members), 2):
            idx.add_edge(a, b, kind, value if kind != "EMAIL" else value)

    # --- shared address (customers / registered corporate addresses)
    addr: dict[str, set[str]] = defaultdict(set)
    for c in db.scalars(select(Customer)):
        if c.address:
            addr[c.address.strip().lower()].add(key("customer", c.id))
    for c in db.scalars(select(Corporate)):
        if c.registered_address:
            addr[c.registered_address.strip().lower()].add(key("corporate", c.id))
    for value, members in addr.items():
        if 2 <= len(members) <= MAX_GROUP["ADDRESS"]:
            for a, b in combinations(sorted(members), 2):
                idx.add_edge(a, b, "ADDRESS", value)

    # --- shared directors / UBOs (ownership data) and customer <-> corporate person matches
    people: dict[tuple, list[tuple[str, OwnershipNode]]] = defaultdict(list)
    for n in db.scalars(select(OwnershipNode).where(OwnershipNode.node_type == "PERSON", OwnershipNode.dob.is_not(None))):  # identity match needs name + DOB
        people[(n.name.strip().lower(), n.dob)].append((key("corporate", n.corporate_id), n))
    for c in db.scalars(select(Customer)):
        for owner, n in people.get((c.full_name.strip().lower(), c.date_of_birth), []):
            kind = "DIRECTOR" if "director" in (n.role or "").lower() else "UBO"
            idx.add_edge(key("customer", c.id), owner, kind, f"{n.name} ({n.role or 'owner'})")
    for (_, _), items in people.items():
        corps = {k for k, _ in items}
        for a, b in combinations(sorted(corps), 2):
            roles = {("DIRECTOR" if "director" in (n.role or "").lower() else "UBO") for _, n in items}
            for kind in roles:
                idx.add_edge(a, b, kind, items[0][1].name)

    # --- shared cash-out: two entities' wallets both pay into the same unlabelled address (no exchange / DeFi attribution)
    labelled = {l.address: l.category for l in db.scalars(select(AddressLabel))}
    owner_of = {w.address: (key("customer", w.customer_id) if w.customer_id else key("corporate", w.corporate_id)) for w in db.scalars(select(Wallet)) if w.customer_id or w.corporate_id}
    payees: dict[str, set[str]] = defaultdict(set)
    for t in db.scalars(select(ChainTx)):
        if t.from_address in owner_of and t.to_address not in owner_of and t.to_address not in labelled:
            payees[t.to_address].add(owner_of[t.from_address])
        if t.from_address in owner_of and t.to_address in owner_of and owner_of[t.from_address] != owner_of[t.to_address]:
            idx.add_edge(owner_of[t.from_address], owner_of[t.to_address], "WALLET", f"direct transfer {t.tx_hash[:12]}")
    for addr_, members in payees.items():
        if 2 <= len(members) <= 6:
            for a, b in combinations(sorted(members), 2):
                idx.add_edge(a, b, "CASHOUT", addr_[:14] + "...")
    idx.finalize()
    return idx


def analyze_entity(db: Session, etype: str, eid: int, hops: int = 2, idx: LinkIndex | None = None, member_scores: dict[str, int] | None = None) -> dict:
    idx = idx or build_index(db)
    k = key(etype, eid)
    if k not in idx.nodes:
        raise LookupError("Entity not found")
    keys = idx.neighborhood(k, hops)
    comp = idx.component(k)
    sc = idx.score(comp, member_scores) if len(comp) > 1 else dict(score=0, level="LOW", components={})
    g = idx.graph(keys)
    for n in g["nodes"]:
        n["is_subject"] = n["key"] == k
    return dict(subject=idx.nodes[k], graph=g, cluster_size=len(comp), cluster=[idx.nodes[x] for x in comp], network_risk=sc,
                hidden_associations=idx.hidden_associations(comp), linked=len(comp) > 1)


def clusters(db: Session, min_score: int = 0, idx: LinkIndex | None = None, member_scores: dict[str, int] | None = None) -> list[dict]:
    idx = idx or build_index(db)
    out = []
    for comp in idx.components(2):
        sc = idx.score(comp, member_scores)
        if sc["score"] < min_score:
            continue
        members = [idx.nodes[k] for k in comp]
        kinds = sorted({r["kind"] for p in idx.edges if p <= set(comp) and idx.strength(p) >= LINK_THRESHOLD for r in idx.edges[p]})
        out.append(dict(id=comp[0], size=len(comp), score=sc["score"], level=sc["level"], members=members, shared=[KIND_LABEL[k] for k in kinds],
                        hidden=len(idx.hidden_associations(comp)), components=sc["components"]))
    return sorted(out, key=lambda c: -c["score"])
