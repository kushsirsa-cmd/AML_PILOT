"""ADVANCED TYPOLOGY AGENT - ten money-laundering / financial-crime typologies, scored from transparent indicators.

Every detection lists the indicators (with points and the transactions / hashes behind them) that produced its score,
so a human can accept, challenge or overrule it. Scores are decision-support, never a finding of guilt.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...data.risk_tables import HIGH_RISK_COUNTRIES, PROHIBITED_COUNTRIES
from ...models import Analysis, Corporate, Customer, ScreeningHit, Transaction, Wallet
from ..txmon import evaluate
from .common import (CASH_INTENSIVE_WORDS, CHARITY_WORDS, CONFLICT_ADJACENT, OFFSHORE, TRADE_INDUSTRY_WORDS, TRAFFICKING_SPEND_WORDS, TRANSIT_HUBS,
                     aware, entity_txs, key, level, load_entity, money, name_of, profile_amount, within)
from .links import LinkIndex, build_index

TYPOLOGIES = {
    "STRUCTURING": ("Structuring", "Breaking cash / transfers into amounts just below reporting thresholds."),
    "SMURFING": ("Smurfing", "Many small deposits by multiple people or accounts, consolidated to one beneficiary."),
    "LAYERING": ("Layering", "Rapid movement and splitting of funds across accounts, jurisdictions or chains to obscure origin."),
    "MULE_ACCOUNT": ("Mule account", "Account used to receive and rapidly forward third-party funds, often as part of a network."),
    "TBML": ("Trade-based money laundering", "Misuse of trade flows (payments, invoicing, routing) to move value across borders."),
    "TERRORIST_FINANCING": ("Terrorist financing indicators", "Low-value, dispersed transfers and attributions consistent with TF typologies (indicator only)."),
    "HUMAN_TRAFFICKING": ("Human trafficking indicators", "Third-party control, cash-intensive small-value flows and travel / accommodation spend (indicator only)."),
    "SANCTIONS_EVASION": ("Sanctions evasion", "Dealings with or on behalf of designated persons, or routing through transit hubs to avoid restrictions."),
    "ROUND_TRIPPING": ("Round tripping", "Funds that leave and return (same or linked party) with no commercial rationale."),
    "CRYPTO_LAUNDERING": ("Crypto laundering", "Mixers, peel chains, darknet / sanctioned exposure and fiat off-ramping of tainted funds."),
}
ALWAYS_HUMAN_MLRO = {"TERRORIST_FINANCING", "SANCTIONS_EVASION"}  # never closed or filed without MLRO judgement


class Det:
    def __init__(self, code: str, caveat: str = ""):
        self.code, self.items, self.caveat = code, [], caveat

    def add(self, points: int, text: str, refs=()):
        self.items.append(dict(points=points, text=text, refs=list(refs)[:25]))

    def result(self) -> dict:
        score = min(100, sum(i["points"] for i in self.items))
        refs = sorted({r for i in self.items for r in i["refs"]})
        conf = 0 if not self.items else min(95, 35 + 12 * len(self.items)) if score >= 35 else score
        label, desc = TYPOLOGIES[self.code]
        return dict(code=self.code, label=label, description=desc, score=score, severity=level(score), confidence=conf, indicators=self.items, refs=refs[:40],
                    caveat=self.caveat, mlro_required=self.code in ALWAYS_HUMAN_MLRO and score >= 35)


class Ctx:
    def __init__(self, db: Session, etype: str, eid: int, idx: LinkIndex):
        self.db, self.etype, self.eid, self.idx = db, etype, eid, idx
        self.obj = load_entity(db, etype, eid)
        self.key = key(etype, eid)
        self.txs = [t for t in entity_txs(db, etype, eid)]
        self.rules = evaluate(self.txs, profile_amount(self.obj))
        self.comp = idx.component(self.key) if idx.adj.get(self.key) else [self.key]
        self.peer_txs: dict[str, list[Transaction]] = {}
        for k in self.comp:
            if k != self.key:
                t, i = k.split(":")
                self.peer_txs[k] = entity_txs(db, t, int(i))
        self.wallets = list(db.scalars(select(Wallet).where((Wallet.customer_id == eid) if etype == "customer" else (Wallet.corporate_id == eid))))
        self.wallet_out: list[dict] = []
        for w in self.wallets:
            a = db.scalar(select(Analysis).where(Analysis.entity_type == "wallet", Analysis.entity_id == w.id).order_by(Analysis.id.desc()).limit(1))
            if a:
                self.wallet_out.append(dict(wallet=w, out=a.output))
        self.hits = list(db.scalars(select(ScreeningHit).where(ScreeningHit.customer_id == eid, ScreeningHit.disposition != "FALSE_POSITIVE"))) if etype == "customer" else []
        self.kyb = None
        if etype == "corporate":
            a = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == eid).order_by(Analysis.id.desc()).limit(1))
            self.kyb = a.output if a else None
        self.industry = (getattr(self.obj, "industry", "") or "").lower()

    def cluster_nodes(self):
        return [self.idx.nodes[k] for k in self.comp]


GENERIC_PARTIES = ("private individual", "unspecified third party", "cash deposit", "landlord")


def _share_out_fast(txs: list[Transaction], hours: int = 48, monthly_income: float | None = None) -> tuple[float, float, list[str]]:
    """Share of third-party inflow value that left the account within `hours` (non-card), greedy matching.
    Salary-sized credits (>= 60% of declared monthly income) and rent / mortgage debits are ordinary life, not pass-through."""
    ins = [t for t in txs if t.direction == "IN" and t.channel != "CARD" and not (monthly_income and t.amount_eur >= 0.6 * monthly_income)]
    outs = [(t, t.amount_eur) for t in txs if t.direction == "OUT" and t.channel != "CARD" and not t.counterparty.lower().startswith("landlord")]
    left = {t.id: amt for t, amt in outs}
    total_in, moved, refs = sum(t.amount_eur for t in ins), 0.0, []
    for i in ins:
        need = i.amount_eur
        for o, _ in outs:
            if need <= 0:
                break
            if within(i.ts, o.ts, hours) and left[o.id] > 0:
                take = min(need, left[o.id])
                left[o.id] -= take
                need -= take
                moved += take
                refs += [i.txn_ref, o.txn_ref]
    return total_in, moved, sorted(set(refs))


def structuring(c: Ctx) -> Det:
    d = Det("STRUCTURING", "Thresholds differ by jurisdiction; confirm the applicable reporting threshold.")
    hits = c.rules.get("STRUCTURING_CASH", [])
    if hits:
        total = sum(t.amount_eur for t in hits)
        d.add(45, f"{len(hits)} cash deposits of EUR 7,000-9,999 within 14 days ({money(total)}), just under the EUR 10,000 threshold", [t.txn_ref for t in hits])
        if total >= 25000:
            d.add(15, f"Combined structured amount {money(total)} is material")
        if len({t.counterparty for t in hits}) > 1:
            d.add(10, "Deposits spread across multiple channels / branches", [t.txn_ref for t in hits])
    small_after = [t for t in c.txs if t.channel == "CASH" and t.direction == "IN" and 4000 <= t.amount_eur < 5000]
    if len(small_after) >= 4:
        d.add(15, f"{len(small_after)} cash deposits just under EUR 5,000", [t.txn_ref for t in small_after])
    for w in c.wallet_out:
        for p in w["out"].get("patterns", []):
            if p["pattern"] == "STRUCTURING":
                d.add(30, f"Wallet {w['wallet'].address[:10]}... shows on-chain structuring (fan-in of deposits under EUR 10,000)", p["tx_hashes"][:10])
                break
    return d


def smurfing(c: Ctx) -> Det:
    d = Det("SMURFING", "Look for the common beneficiary and who instructed the small deposits.")
    ins = [t for t in c.txs if t.direction == "IN" and t.channel in ("SEPA", "WIRE", "CASH") and t.amount_eur < 5000]
    sources = Counter(t.counterparty for t in ins if t.counterparty and not t.counterparty.lower().startswith("cash deposit"))
    if len(sources) >= 5 and sum(t.amount_eur for t in ins) >= 8000:
        d.add(30, f"Receives many small credits ({len(ins)}) from {len(sources)} different counterparties", [t.txn_ref for t in ins])
        monthly = (c.obj.annual_income / 12) if isinstance(c.obj, Customer) and c.obj.annual_income else None
        total_in, moved, refs = _share_out_fast(c.txs, 72, monthly)
        total_in = total_in or 1
        if moved / total_in >= 0.7:
            d.add(25, f"{moved / total_in:.0%} of inflow consolidated and forwarded within 72 hours", refs)
    cash_in = [t for t in c.txs if t.channel == "CASH" and t.direction == "IN" and 2000 <= t.amount_eur < 5000]
    if len(cash_in) >= 5 and len(c.comp) >= 3:
        d.add(25, f"{len(cash_in)} small cash deposits while part of a {len(c.comp)}-entity network", [t.txn_ref for t in cash_in])
    # network-level smurfing: several linked entities depositing small amounts to the same onward beneficiary
    peers_with_small = [k for k, txs in c.peer_txs.items() if sum(1 for t in txs if t.direction == "IN" and 2000 <= t.amount_eur < 5000 and t.channel in ("CASH", "SEPA")) >= 4]
    if len(peers_with_small) >= 2:
        d.add(25, f"{len(peers_with_small)} linked entities show the same pattern of repeated small deposits", [])
    return d


def layering(c: Ctx) -> Det:
    d = Det("LAYERING", "Rapid movement can be legitimate for payment processors / agents - check the business model.")
    rp = c.rules.get("RAPID_PASS_THROUGH", [])
    if rp:
        d.add(35, f"Rapid pass-through: {money(rp[0].amount_eur)} in, >=85% out within 48 hours", [t.txn_ref for t in rp])
    outs = [t for t in c.txs if t.direction == "OUT" and t.channel in ("WIRE", "SEPA")]
    for t0 in outs:
        window = [t for t in outs if within(t0.ts, t.ts, 72)]
        if len({t.counterparty for t in window}) >= 3 and len({t.counterparty_country for t in window}) >= 2 and sum(t.amount_eur for t in window) >= 20000:
            d.add(25, f"Funds split to {len({t.counterparty for t in window})} recipients in {len({t.counterparty_country for t in window})} countries within 72 hours ({money(sum(t.amount_eur for t in window))})", [t.txn_ref for t in window])
            break
    inter = [t for t in outs if any(w in t.counterparty.lower() for w in ("intermediary", "holdings", "offshore")) and t.counterparty_country.lower() in OFFSHORE]
    if inter:
        d.add(10, "Onward payments to intermediary / holding companies in offshore jurisdictions", [t.txn_ref for t in inter])
    for w in c.wallet_out:
        pats = {p["pattern"] for p in w["out"].get("patterns", [])}
        if "PEEL_CHAIN" in pats:
            d.add(30, f"Wallet {w['wallet'].address[:10]}... shows a peel-chain (sequential splitting through intermediate addresses)", [h for p in w["out"]["patterns"] if p["pattern"] == "PEEL_CHAIN" for h in p["tx_hashes"]][:10])
        elif "RAPID_PASS_THROUGH" in pats:
            d.add(20, f"Wallet {w['wallet'].address[:10]}... forwards received value within hours", [])
    return d


def mule(c: Ctx) -> Det:
    d = Det("MULE_ACCOUNT", "Mules are often victims or recruited unknowingly - treat the account holder with care.")
    monthly = (c.obj.annual_income / 12) if isinstance(c.obj, Customer) and c.obj.annual_income else None
    ins = [t for t in c.txs if t.direction == "IN" and t.channel in ("SEPA", "WIRE", "CASH") and t.counterparty and not t.counterparty.lower().startswith("cash deposit")
           and not (monthly and t.amount_eur >= 0.6 * monthly)]
    sources = {t.counterparty for t in ins}
    if len(sources) >= 4:
        total_in, moved, refs = _share_out_fast(c.txs, 48, monthly)
        share = moved / total_in if total_in else 0
        if share >= 0.75:
            d.add(35, f"Receives from {len(sources)} unrelated counterparties and forwards {share:.0%} within 48 hours", refs)
            profile = profile_amount(c.obj) or 0
            low_profile = (isinstance(c.obj, Customer) and profile < 30000) or any(w in (getattr(c.obj, "occupation", "") or "").lower() for w in ("student", "unemployed", "retired", "intern"))
            if low_profile:
                d.add(15, f"Account activity ({money(total_in)}) is out of proportion to the declared profile ({money(profile)}/yr)", [])
            dests = Counter(t.counterparty_country for t in c.txs if t.direction == "OUT" and t.channel in ("WIRE", "SEPA"))
            if dests and dests.most_common(1)[0][0].lower() not in ("poland",) and dests.most_common(1)[0][1] >= 2:
                d.add(10, f"Outbound transfers concentrated in {dests.most_common(1)[0][0]}", [])
    shared = [k for k in c.comp if k != c.key and c.idx.nodes[k]["type"] == "customer"]
    if shared and d.items:
        mule_like = [k for k in shared if len({t.counterparty for t in c.peer_txs.get(k, []) if t.direction == "IN"}) >= 4]
        if mule_like:
            d.add(25, f"{len(mule_like)} other account(s) linked by shared identifiers show the same receive-and-forward behaviour: a mule network", [])
    return d


def tbml(c: Ctx) -> Det:
    d = Det("TBML", "Requires trade documents (invoices, bills of lading, customs data) to confirm or refute - a human review step.")
    if not any(w in c.industry for w in TRADE_INDUSTRY_WORDS):
        return d
    wires = [t for t in c.txs if t.channel in ("WIRE", "SEPA")]
    declared = {x.strip().lower() for x in (getattr(c.obj, "operating_countries", "") or "").split(",") if x.strip()}
    foreign = [t for t in wires if t.counterparty_country.lower() not in declared | {"poland"} and t.amount_eur >= 5000]
    countries = {t.counterparty_country for t in foreign}
    if len(countries) >= 3:
        d.add(25, f"Trade payments to {len(countries)} countries outside the declared operating footprint: {', '.join(sorted(countries))}", [t.txn_ref for t in foreign])
    hubs = [t for t in wires if t.counterparty_country.lower() in TRANSIT_HUBS or t.counterparty_country.lower() in HIGH_RISK_COUNTRIES]
    if len(hubs) >= 3:
        d.add(20, f"{len(hubs)} payments routed through transit / high-risk hubs", [t.txn_ref for t in hubs])
    rnd = [t for t in wires if t.amount_eur >= 10000 and t.amount_eur % 5000 == 0]
    if len(rnd) >= 3 and len(rnd) / max(1, len(wires)) >= 0.4:
        d.add(10, f"{len(rnd)} round-sum trade payments - invoice amounts are rarely round", [t.txn_ref for t in rnd])
    turnover = profile_amount(c.obj) or 0
    recent_in = sum(t.amount_eur for t in wires if t.direction == "IN")
    if turnover and recent_in > turnover / 4 * 1.5:
        d.add(15, f"Inflows {money(recent_in)} exceed the declared quarterly turnover ({money(turnover / 4)}) by >50%", [])
    if c.rules.get("RAPID_PASS_THROUGH") and d.items:
        d.add(15, "Funds pass straight through the account - no evidence of goods being bought or sold", [t.txn_ref for t in c.rules["RAPID_PASS_THROUGH"]])
    return d


def terror(c: Ctx) -> Det:
    d = Det("TERRORIST_FINANCING", "INDICATOR ONLY. Many legitimate donors and diaspora remitters share these features. Decision rests with the MLRO / FIU; terrorism-related suspicions follow dedicated reporting and tipping-off rules.")
    small = [t for t in c.txs if t.direction == "OUT" and t.channel in ("WIRE", "SEPA", "CRYPTO_OFFRAMP") and t.amount_eur <= 1500]
    adj = [t for t in small if t.counterparty_country.lower() in CONFLICT_ADJACENT]
    if len(adj) >= 4 and len({t.counterparty for t in adj}) >= 3:
        d.add(30, f"{len(adj)} low-value transfers (<= EUR 1,500) to {len({t.counterparty for t in adj})} different recipients in jurisdictions adjacent to conflict zones", [t.txn_ref for t in adj])
        charity = [t for t in adj if any(w in t.counterparty.lower() for w in CHARITY_WORDS)]
        if charity:
            d.add(15, "Recipients present as relief / charitable collectives - verify registration and end-use", [t.txn_ref for t in charity])
        if len({aware(t.ts).date().isoformat()[:7] for t in adj}) <= 2:
            d.add(10, "Transfers are clustered in a short period", [])
    for w in c.wallet_out:
        src = w["out"].get("exposure", {}).get("sources_total_pct", {})
        if src.get("TERRORISM_FINANCING", 0) > 0:
            d.add(60, f"Wallet {w['wallet'].address[:10]}... has exposure to addresses attributed to terrorism financing", [])
    for h in c.hits:
        rec = (h.details or {}).get("record", {})
        text = " ".join(str(v) for v in rec.values()).lower()
        if "terror" in text and h.confidence >= 75:
            d.add(40, f"Screening match ({h.confidence:.0f}%) with a terrorism-related designation / media report: {h.matched_name}", [])
    return d


def trafficking(c: Ctx) -> Det:
    d = Det("HUMAN_TRAFFICKING", "INDICATOR ONLY. Indicators are drawn from FATF / industry guidance and are individually ambiguous. Victim welfare comes first; escalate to the MLRO and consider law-enforcement liaison.")
    cash = [t for t in c.txs if t.channel == "CASH" and t.direction == "IN" and t.amount_eur < 1000]
    if len(cash) >= 8:
        d.add(15, f"{len(cash)} small cash deposits (<EUR 1,000) - frequent, low-value, cash-based", [t.txn_ref for t in cash])
    spend = [t for t in c.txs if t.direction == "OUT" and any(w in t.counterparty.lower() for w in TRAFFICKING_SPEND_WORDS)]
    if len(spend) >= 3:
        d.add(20, f"{len(spend)} payments for accommodation / transport / online classifieds", [t.txn_ref for t in spend])
    if any(w in c.industry for w in CASH_INTENSIVE_WORDS) or any(w in (getattr(c.obj, "occupation", "") or "").lower() for w in CASH_INTENSIVE_WORDS):
        if d.items:
            d.add(10, "Cash-intensive occupation / sector", [])
    remit = [t for t in c.txs if t.direction == "OUT" and t.channel in ("WIRE", "SEPA") and t.amount_eur <= 2000 and t.counterparty_country.lower() != "poland"]
    if len(remit) >= 4 and len({t.counterparty for t in remit}) >= 3:
        d.add(10, f"Recurring small remittances to {len({t.counterparty for t in remit})} individuals in {len({t.counterparty_country for t in remit})} countries", [t.txn_ref for t in remit])
    for h in c.hits:
        rec = (h.details or {}).get("record", {})
        if h.list_type == "ADVERSE_MEDIA" and any(w in str(rec).lower() for w in ("traffick", "exploitation", "forced labour")):
            d.add(30, f"Adverse media references trafficking / exploitation: {rec.get('headline', h.matched_name)}", [])
    linked = [k for k in c.comp if k != c.key and c.idx.nodes[k]["type"] == "customer"]
    if linked and d.items:  # network sharing only corroborates behavioural indicators - on its own it is not a trafficking signal
        edges = [c.idx.edge(c.key, k) for k in linked if k in c.idx.adj.get(c.key, ())]
        third_party = [e for e in edges if not e["declared"] and any(r["kind"] in ("DEVICE", "PHONE", "ADDRESS") for r in e["reasons"])]
        if len(third_party) >= 2:
            d.add(25, f"Shares device / phone / address with {len(third_party)} unrelated customers (possible third-party control of accounts)", [])
    return d


def sanctions(c: Ctx) -> Det:
    d = Det("SANCTIONS_EVASION", "A designation match must be confirmed by the sanctions team; potential breaches may require freezing and reporting without delay.")
    strong = [h for h in c.hits if h.list_type == "SANCTIONS" and (h.confidence >= 90 or h.disposition == "CONFIRMED")]
    near = [h for h in c.hits if h.list_type == "SANCTIONS" and 65 <= h.confidence < 90 and h not in strong]
    if strong:
        d.add(50, f"Sanctions screening match {strong[0].confidence:.0f}% - {strong[0].matched_name}", [])
    elif near:
        d.add(10, f"Possible sanctions name match ({near[0].confidence:.0f}%) not yet resolved", [])
    risky_w = [t for t in c.txs if t.channel in ("WIRE", "SEPA") and t.counterparty_country.lower() in PROHIBITED_COUNTRIES | {"russia", "belarus"}]
    if risky_w:
        d.add(20, f"{len(risky_w)} payments to / from sanctioned or comprehensively-restricted jurisdictions", [t.txn_ref for t in risky_w])
    via_hub = [t for t in c.txs if t.channel in ("WIRE", "SEPA") and t.counterparty_country.lower() in TRANSIT_HUBS]
    if via_hub and (strong or risky_w or any(n["key"] in c.idx.sanctioned for n in c.cluster_nodes())):
        d.add(15, f"{len(via_hub)} payments routed via transit hubs ({', '.join(sorted({t.counterparty_country for t in via_hub}))})", [t.txn_ref for t in via_hub])
    for w in c.wallet_out:
        src = w["out"].get("exposure", {}).get("sources_total_pct", {})
        if src.get("SANCTIONED", 0) > 0 or any(t["category"] == "SANCTIONED" for t in w["out"].get("risky_traces", [])):
            d.add(40, f"Wallet {w['wallet'].address[:10]}... received funds traced to a designated entity", [])
    if c.kyb:
        codes = {f["code"] for f in c.kyb["structure"]["red_flags"]}
        if codes & {"NOMINEES", "CIRCULAR_OWNERSHIP", "SECRECY_JURISDICTION", "NO_UBO_IDENTIFIED"} and d.items:
            d.add(15, "Opaque ownership structure (nominees / circular holding / secrecy jurisdiction)", [])
        for h in c.kyb.get("screening_hits", []):
            if h["list_type"] == "SANCTIONS" and h["confidence"] >= 85:
                d.add(45, f"Beneficial owner / director matches a designation: {h['party']} ~ {h['matched_name']} ({h['confidence']:.0f}%)", [])
    linked_sanc = [n for n in c.cluster_nodes() if n["key"] != c.key and n["key"] in c.idx.sanctioned]
    if linked_sanc:
        d.add(30, f"Linked by shared identifiers / ownership to a screening-match entity: {linked_sanc[0]['name']}", [])
    return d


def round_trip(c: Ctx) -> Det:
    d = Det("ROUND_TRIPPING", "Genuine back-to-back contracts, loans and refunds can look similar - ask for the commercial rationale and contracts.")
    outs = [t for t in c.txs if t.direction == "OUT" and t.channel in ("WIRE", "SEPA") and t.amount_eur >= 10000]
    linked_names = {c.idx.nodes[k]["name"].lower() for k in c.comp if k != c.key}
    for o in outs:
        if o.counterparty.lower() in GENERIC_PARTIES or any(g in o.counterparty.lower() for g in GENERIC_PARTIES):
            continue
        back = [t for t in c.txs if t.direction == "IN" and t.channel in ("WIRE", "SEPA") and 0 < (aware(t.ts) - aware(o.ts)).days <= 30
                and 0.9 * o.amount_eur <= t.amount_eur <= 1.1 * o.amount_eur
                and (t.counterparty.lower() == o.counterparty.lower() or t.counterparty.lower() in linked_names or o.counterparty.lower() in linked_names)]
        if back:
            d.add(50, f"{money(o.amount_eur)} sent to {o.counterparty} returned ({money(back[0].amount_eur)}) within {(aware(back[0].ts) - aware(o.ts)).days} days", [o.txn_ref, back[0].txn_ref])
            if o.counterparty.lower() in linked_names or back[0].counterparty.lower() in linked_names:
                d.add(25, "The counterparty is linked to the customer by shared directors / UBOs / identifiers", [])
            break
    return d


def crypto(c: Ctx) -> Det:
    d = Det("CRYPTO_LAUNDERING", "Attribution data is simulated in this prototype; in production confirm with at least two chain-analytics providers.")
    for w in c.wallet_out:
        o = w["out"]
        pts = {"SEVERE": 45, "HIGH": 30, "MEDIUM": 10}.get(o["risk_level"], 0)
        if pts:
            d.add(pts, f"Wallet {w['wallet'].address[:10]}... screened {o['risk_level']} (score {o['risk_score']})", [])
        src = o.get("exposure", {}).get("sources_total_pct", {})
        for cat, p in (("MIXER", 15), ("DARKNET", 20), ("RANSOMWARE", 25), ("SCAM", 15)):
            if src.get(cat, 0) >= 3 or any(t["category"] == cat for t in o.get("risky_traces", [])):
                d.add(p, f"Exposure to {cat.lower()} addresses", [])
        for pat in o.get("patterns", []):
            if pat["pattern"] in ("PEEL_CHAIN", "RAPID_PASS_THROUGH", "STRUCTURING"):
                d.add(10, f"On-chain pattern: {pat['pattern'].replace('_', ' ').lower()}", pat["tx_hashes"][:6])
    off = [t for t in c.txs if t.channel == "CRYPTO_OFFRAMP"]
    if off and d.items:
        d.add(15, f"{len(off)} fiat off-ramp credits ({money(sum(t.amount_eur for t in off))}) alongside risky wallet activity", [t.txn_ref for t in off])
    return d


DETECTORS = (structuring, smurfing, layering, mule, tbml, terror, trafficking, sanctions, round_trip, crypto)


def detect(db: Session, etype: str, eid: int, idx: LinkIndex | None = None) -> dict:
    """Run all ten typology detectors for one customer / corporate."""
    c = Ctx(db, etype, eid, idx or build_index(db))
    results = [fn(c).result() for fn in DETECTORS]
    scores = {r["code"]: r["score"] for r in results}
    detections = sorted((r for r in results if r["score"] >= 25), key=lambda r: -r["score"])
    prod = 1.0
    for r in detections:
        prod *= 1 - min(0.95, r["score"] / 100 * 0.9)
    overall = round(100 * (1 - prod)) if detections else (max(scores.values()) if scores else 0)
    if any(r["mlro_required"] for r in detections) or overall >= 80:
        rec, why = "ESCALATE_MLRO", "Terrorism-financing / sanctions indicators or very high composite score - MLRO judgement required."
    elif overall >= 50:
        rec, why = "ESCALATE_FIU", "Multiple corroborating indicators - refer to the FIU for full investigation."
    elif overall >= 25:
        rec, why = "ENHANCED_MONITORING", "Some indicators present but not corroborated - enhanced monitoring and a periodic re-check."
    else:
        rec, why = "NO_ACTION", "No typology reached the reporting threshold."
    return dict(subject=dict(type=etype, id=eid, name=name_of(c.obj), rating=getattr(c.obj, "risk_rating", None)), scores=scores, detections=detections,
                typologies=[r["code"] for r in detections], risk_score=overall, severity=level(overall),
                escalation=dict(recommendation=rec, rationale=why, human_decision_required=True), network_size=len(c.comp))
