"""Phase-4 demo data: shared identifiers, planted laundering networks and typology scenarios.

Everything is synthetic. Network members are *ordinary-looking, individually low-risk* customers on purpose - the
point of the FIU demo is that the risk only becomes visible when you link them (hidden association detection).
Identifiers use reserved documentation ranges (RFC 5737 IPs, fake IBAN-style strings) and fictional names.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AddressLabel, ChainTx, Corporate, Customer, EntityIdentifier, OwnershipNode, Transaction

NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
PRIVATE_NAMES = ["Tomasz Lis", "Agnieszka Duda", "Paweł Kubiak", "Ewa Sadowska", "Marcin Wolski", "Karolina Zając", "Jakub Mazur", "Oliwia Pietrzak", "Dawid Sikora",
                 "Natalia Kaczmarek", "Michał Wróbel", "Joanna Walczak", "Krzysztof Adamski", "Zofia Baran", "Bartosz Jaworski", "Alicja Kołodziej", "Szymon Michalak", "Magdalena Rutkowska"]
AID_NAMES = ["Hope Relief Collective", "Aid Bridge Foundation", "Humanitarian Fund Amman", "Beirut Relief Circle", "Anatolia Donation Fund", "Safe Passage Aid", "Compassion Charity Group"]


def _h(s: str, n: int = 8) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def pick_scenarios(db: Session) -> dict:
    """Deterministically choose the ordinary customers / corporates that play each scenario."""
    active = [c for c in db.scalars(select(Customer).where(Customer.status == "ACTIVE").order_by(Customer.id)) if c.risk_rating in ("LOW", "MEDIUM") and c.id > 11]
    corps = [k for k in db.scalars(select(Corporate).where(Corporate.status == "ACTIVE").order_by(Corporate.id)) if k.id > 5]
    trade = [k for k in corps if any(w in (k.industry or "").lower() for w in ("trading", "import", "freight", "logistics", "automotive"))]
    out = dict(mule=active[0:5], smurf=active[5:11], smurf_benef=active[11:12], traffic=active[12:15], tf=active[15:16], family_a=active[16:18], family_b=active[18:20])
    pair = [k for k in corps if k not in trade[:1]][:2]
    out.update(round_pair=pair, tbml=trade[:1])
    named = {c.full_name: c for c in db.scalars(select(Customer).where(Customer.id <= 11))}
    corp_named = {k.legal_name: k for k in db.scalars(select(Corporate).where(Corporate.id <= 5))}
    out.update(kozlov=named.get("Viktor Kozlov"), baltic=corp_named.get("Baltic Trade Ventures OÜ"))
    return out


def seed_identifiers(db: Session) -> int:
    sc = pick_scenarios(db)
    rows: list[tuple[str, int, str, str, str]] = []

    def add(e, kind, value, src="ONBOARDING"):
        et = "customer" if isinstance(e, Customer) else "corporate"
        rows.append((et, e.id, kind, value, src))

    for c in db.scalars(select(Customer)):
        h = _h(f"c{c.id}", 8)
        add(c, "PHONE", f"+48 {500 + int(h[:2], 16) % 400} {int(h[2:5], 16) % 900 + 100:03d} {int(h[5:8], 16) % 900 + 100:03d}")
        add(c, "EMAIL", f"{c.full_name.lower().replace(' ', '.').replace('ł', 'l').replace('ó', 'o')}.{h[:3]}@mail.example")
        add(c, "IP", f"31.{int(h[:2], 16)}.{int(h[2:4], 16)}.{int(h[4:6], 16) % 250 + 1}", "SESSION_LOG")
        add(c, "DEVICE", f"DV-{_h(f'dev{c.id}', 10)}", "SESSION_LOG")
    for k in db.scalars(select(Corporate)):
        h = _h(f"k{k.id}", 8)
        add(k, "PHONE", f"+48 22 {int(h[:3], 16) % 900 + 100:03d} {int(h[3:6], 16) % 90 + 10:02d} {int(h[6:8], 16) % 90 + 10:02d}")
        add(k, "EMAIL", f"office@{_h(k.legal_name, 6)}.example")
        add(k, "IP", f"85.{int(h[:2], 16)}.{int(h[2:4], 16)}.{int(h[4:6], 16) % 250 + 1}", "SESSION_LOG")
    db.flush()
    existing = {(r[0], r[1], r[2]) for r in rows}

    def share(members, kind, value, src="ONBOARDING"):
        for e in members:
            et = "customer" if isinstance(e, Customer) else "corporate"
            # replace the member's own unique value of that kind with the shared one
            for i, r in enumerate(rows):
                if r[0] == et and r[1] == e.id and r[2] == kind and kind != "BANK_ACCOUNT":
                    rows[i] = (et, e.id, kind, value, src)
                    break
            else:
                rows.append((et, e.id, kind, value, src))

    m = sc["mule"]
    share(m[0:3], "DEVICE", "DV-7781ac01e9", "SESSION_LOG")
    share(m[1:4], "PHONE", "+48 600 100 200")
    share(m[2:5], "IP", "203.0.113.47", "SESSION_LOG")
    share(m, "BANK_ACCOUNT", "AE00-DEMO-RAPID-SETTLE-0001", "PAYMENT_DATA")
    s = sc["smurf"] + sc["smurf_benef"]
    share(s[0:4], "IP", "198.51.100.23", "SESSION_LOG")
    share(s[0:3], "PHONE", "+48 601 555 010")
    share(s, "BANK_ACCOUNT", "PL00-DEMO-COBALT-COLLECT-0002", "PAYMENT_DATA")
    t = sc["traffic"]
    share(t, "DEVICE", "DV-5503bd7712", "SESSION_LOG")
    share(t[0:2], "PHONE", "+48 602 777 031")
    addr = "ul. Wspólna 14/3, 31-001 Kraków"
    for e in t:
        e.address = addr
    for fam, ip, phone in ((sc["family_a"], "31.222.10.5", None), (sc["family_b"], "31.222.10.9", None)):
        share(fam, "IP", ip, "SESSION_LOG")
        fa = fam[0].address
        for e in fam[1:]:
            e.address = fa
    if sc["kozlov"] and sc["baltic"]:
        share([sc["kozlov"], sc["baltic"]], "PHONE", "+357 99 123 456")
        share([sc["kozlov"], sc["baltic"]], "BANK_ACCOUNT", "CY00-DEMO-NEVA-CAPITAL-0007", "PAYMENT_DATA")
        share([sc["kozlov"], sc["baltic"]], "IP", "192.0.2.77", "SESSION_LOG")
    # shared director across the round-tripping pair (declared in ownership data)
    for k in sc["round_pair"]:
        if not db.scalar(select(OwnershipNode).where(OwnershipNode.corporate_id == k.id, OwnershipNode.node_key == "DIR_SHARED")):
            db.add(OwnershipNode(corporate_id=k.id, node_key="DIR_SHARED", name="Aleksander Brzezinski", node_type="PERSON", country="Poland", dob=date(1971, 5, 14),
                                 role="Director", id_verified=True))
    seen = set()
    for et, eid, kind, value, src in rows:
        if (et, eid, kind, value) in seen:
            continue
        seen.add((et, eid, kind, value))
        db.add(EntityIdentifier(entity_type=et, entity_id=eid, kind=kind, value=value, source=src))
    db.flush()
    return len(seen)


def scenario_transactions(db: Session, tx) -> None:
    """Called from demo_data.create_transactions with its `tx(ent, days_ago, direction, amount, channel, cp, country, hour)` helper."""
    sc = pick_scenarios(db)
    r = random.Random(4242)
    # 1. Mule network - each account receives from many private individuals, forwards ~93% within a day to one offshore settlement account
    for i, e in enumerate(sc["mule"]):
        for cyc, base in enumerate((14 - i, 6 - i // 2)):
            total = 0.0
            for j in range(3):
                amt = round(r.uniform(420, 2300), 0)
                total += amt
                tx(e, max(1, base) + 0, "IN", amt, "SEPA", PRIVATE_NAMES[(i * 5 + cyc * 3 + j) % len(PRIVATE_NAMES)], "Poland", 20 - j)
            tx(e, max(1, base), "OUT", round(total * 0.93, 0), "WIRE", "Rapid Settle FZE", "United Arab Emirates", 3)
    # 2. Smurfing - six accounts deposit cash just under EUR 5,000 then pay one beneficiary who forwards it to a Cyprus holding
    benef = sc["smurf_benef"][0]
    paid = 0.0
    for i, e in enumerate(sc["smurf"]):
        total = 0.0
        for j in range(5):
            amt = round(r.uniform(2600, 4700), -1)
            total += amt
            tx(e, 12 - j * 2 - (i % 2), "IN", amt, "CASH", f"Cash deposit - branch {1 + (i + j) % 4}", "Poland", 10 + j)
        send = round(total * 0.88, 0)
        paid += send
        tx(e, 2 + (i % 3), "OUT", send, "SEPA", benef.full_name, "Poland", 11)
        tx(benef, 2 + (i % 3), "IN", send, "SEPA", e.full_name, "Poland", 12)
    tx(benef, 1, "OUT", round(paid * 0.92, 0), "WIRE", "Cobalt Holdings Ltd", "Cyprus", 8)
    # 3. Human-trafficking indicators - small frequent cash, accommodation / transport payments, small remittances (accounts share a device, phone and address)
    for i, e in enumerate(sc["traffic"]):
        for d in range(9):
            tx(e, 28 - d * 3 - i, "IN", r.choice([180, 240, 320, 450, 610, 780]), "CASH", f"Cash deposit - branch {1 + d % 3}", "Poland", 17)
        for d, cp in enumerate(["Budget Hotel Krakow", "Euro Airlines", "City Hostel Prague", "Regional Bus Tickets"]):
            tx(e, 24 - d * 5 - i, "OUT", r.choice([95, 140, 210, 260]), "CARD", cp, "Poland", 19)
        for d, (cp, country) in enumerate([("A. Ionescu", "Italy"), ("M. Petrov", "Czechia"), ("L. Moreno", "Spain"), ("D. Novak", "Germany")]):
            tx(e, 20 - d * 4 - i, "OUT", r.choice([300, 450, 600]), "WIRE", cp, country, 13)
    # 4. Terrorist-financing indicators - low-value dispersed transfers to relief collectives adjacent to a conflict zone
    for e in sc["tf"]:
        for d, (cp, country) in enumerate(zip(AID_NAMES, ["Turkey", "Lebanon", "Jordan", "Turkey", "Lebanon", "Jordan", "Turkey"])):
            tx(e, 21 - d * 3, "OUT", r.choice([250, 400, 520, 700, 900]), "WIRE", cp, country, 11)
    # 5. Round tripping - two companies with a shared director pay each other the same money back and forth
    if len(sc["round_pair"]) == 2:
        a, b = sc["round_pair"]
        tx(a, 24, "OUT", 150000, "WIRE", b.legal_name, b.country_of_incorporation, 10)
        tx(b, 24, "IN", 150000, "WIRE", a.legal_name, a.country_of_incorporation, 11)
        tx(b, 11, "OUT", 147500, "WIRE", a.legal_name, a.country_of_incorporation, 10)
        tx(a, 11, "IN", 147500, "WIRE", b.legal_name, b.country_of_incorporation, 11)
    # 6. Trade-based ML - round-sum payments to four countries outside the operating footprint, funds passing straight through
    for k in sc["tbml"]:
        turnover = k.annual_turnover or 800000
        tx(k, 38, "IN", round(turnover * 0.45, -3), "WIRE", "Eurasia Sourcing FZE", "United Arab Emirates", 9)
        tx(k, 37, "OUT", 60000, "WIRE", "Pearl Delta Trading Co", "Hong Kong", 9)
        tx(k, 37, "OUT", 40000, "WIRE", "Bosphorus Metals AS", "Turkey", 10)
        tx(k, 30, "IN", round(turnover * 0.4, -3), "WIRE", "Eurasia Sourcing FZE", "United Arab Emirates", 9)
        tx(k, 29, "OUT", 50000, "WIRE", "Isthmus Marine Supply SA", "Panama", 11)
        tx(k, 29, "OUT", 45000, "WIRE", "Pearl Delta Trading Co", "Hong Kong", 12)
        tx(k, 20, "IN", round(turnover * 0.35, -3), "WIRE", "Eurasia Sourcing FZE", "United Arab Emirates", 9)
        tx(k, 19, "OUT", 70000, "WIRE", "Anatolia Components AS", "Turkey", 10)
        tx(k, 19, "OUT", 40000, "WIRE", "Isthmus Marine Supply SA", "Panama", 11)
    # 7. Sanctions-evasion network - Viktor Kozlov and Baltic Trade Ventures move money through the same Cyprus intermediary
    if sc["kozlov"] and sc["baltic"]:
        tx(sc["kozlov"], 5, "OUT", 21000, "WIRE", "Neva Capital Partners Ltd", "Cyprus", 10)
        tx(sc["baltic"], 4, "IN", 20500, "WIRE", "Neva Capital Partners Ltd", "Cyprus", 9)


def seed_chain_extras(db: Session) -> None:
    """Cross-chain scenario on the existing Lena Hoffmann wallet: ETH -> bridge -> BTC -> mixer / unlicensed OTC. Attribution is simulated."""
    from .modules.chain_sim import A
    labels = {
        A("bridge_eth"): ("ETH", "BRIDGE", "ChainHop Bridge (ETH deposit)"),
        A("bridge_btc", "BTC"): ("BTC", "BRIDGE", "ChainHop Bridge (BTC payout)"),
        A("btc_mix", "BTC"): ("BTC", "MIXER", "BitSwirl mixer (BTC)"),
        A("btc_otc", "BTC"): ("BTC", "UNREGULATED_EXCHANGE", "QuickOTC (unlicensed, BTC)"),
    }
    for addr, (chain, cat, name) in labels.items():
        if not db.get(AddressLabel, addr):
            db.add(AddressLabel(address=addr, chain=chain, category=cat, entity_name=name, source="SIMULATED-ATTRIBUTION"))
    if db.scalar(select(ChainTx).where(ChainTx.tx_hash == "0x" + hashlib.sha256(b"xchain-1").hexdigest())):
        return
    now = NOW

    def ctx(n, frm, to, chain, asset, eur, days, hours=0.0):
        price = {"BTC": 90000.0, "ETH": 3000.0, "USDT": 1.0}[asset]
        db.add(ChainTx(tx_hash="0x" + hashlib.sha256(f"xchain-{n}".encode()).hexdigest(), chain=chain, from_address=frm, to_address=to, asset=asset,
                       amount=round(eur / price, 6), amount_eur=eur, ts=now - timedelta(days=days) + timedelta(hours=hours)))

    # Lena's wallet moves 25k to the bridge on ETH; 24.2k arrives from the bridge on BTC an hour later; split to a mixer and an unlicensed OTC
    ctx(1, A("wL1"), A("bridge_eth"), "ETH", "USDT", 25000, 12)
    ctx(2, A("bridge_btc", "BTC"), A("btc_h1", "BTC"), "BTC", "BTC", 24200, 12, 1.2)
    ctx(3, A("btc_h1", "BTC"), A("btc_mix", "BTC"), "BTC", "BTC", 12000, 11.9)
    ctx(4, A("btc_h1", "BTC"), A("btc_otc", "BTC"), "BTC", "BTC", 12000, 11.8)
    ctx(5, A("btc_mix", "BTC"), A("btc_h2", "BTC"), "BTC", "BTC", 11700, 11.5)
    ctx(6, A("btc_h2", "BTC"), A("btc_otc", "BTC"), "BTC", "BTC", 11600, 11.2)
    db.flush()


def seed_investigations(db: Session) -> int:
    """~14 back-dated investigations spread over every queue (including closed), driven through the real lifecycle code."""
    from . import audit
    from .models import Alert, Investigation, Sar
    from .modules.fiu import cases
    if db.scalar(select(Investigation.id).limit(1)):
        return 0
    sc = pick_scenarios(db)
    idx = None
    made = 0

    def alert_for(et, eid):
        return db.scalar(select(Alert).where(Alert.entity_type == et, Alert.entity_id == eid, Alert.status == "OPEN").order_by(Alert.id))

    def start(who, days, src="RBI", title=None):
        nonlocal made
        if who is None:
            return None
        et = "customer" if isinstance(who, Customer) else "corporate"
        a = alert_for(et, who.id)
        try:
            inv = cases.open_case(db, "analyst.demo", alert_id=a.id if a else None, entity_type=et, entity_id=who.id, source_type=None if a else src, title=title)
        except cases.CaseError:
            return None
        inv.created_at = NOW - timedelta(days=days)
        made += 1
        return inv

    def do(inv, user, action, text=None, disp=None):
        try:
            cases.act(db, user, inv, action, text, disp)
        except cases.CaseError:
            pass

    def to_fiu(inv):
        do(inv, "analyst.demo", "accept_to_fiu", "Triage: corroborated by typology engine; proceeding to FIU investigation.")

    def to_esc(inv, why):
        to_fiu(inv); do(inv, "senior.demo", "escalate", why)

    def to_sar(inv, why):
        to_esc(inv, why); do(inv, "senior.demo", "to_sar", "SAR drafted for MLRO.")

    def pend(inv):
        s = db.get(Sar, inv.sar_id) if inv.sar_id else None
        if s and s.status == "DRAFT":
            s.status, s.submitted_at = "PENDING_MLRO", NOW - timedelta(days=2)
            audit.log(db, actor="senior.demo", actor_type=audit.USER, action="SAR_SUBMITTED", entity_type="sar", entity_id=s.id, customer_id=s.customer_id, details={"reference": s.reference})

    k = start(sc["baltic"], 41, "FIU", "Baltic Trade Ventures - sanctioned-network exposure")          # SAR filed
    if k:
        to_sar(k, "Shared UBO/director and wallet links to sanctioned Kozlov network; TBML and layering indicators.")
        pend(k)
        s = db.get(Sar, k.sar_id) if k.sar_id else None
        if s:
            s.status, s.approved_by, s.mlro_note, s.decided_at = "FILED", "mlro.demo", "Suspicion established; filing approved.", NOW - timedelta(days=30)
            s.filing_reference = f"FIU-SIM-{NOW:%Y%m%d}-{s.id:04d}"; s.filed_at = NOW - timedelta(days=30)
            cases.sync(db, k)
    v = start(sc["kozlov"], 12, "FIU")                                                               # waiting for the MLRO
    if v:
        to_sar(v, "Sanctions-evasion indicators with undeclared associations; mandatory MLRO judgement."); pend(v); cases.sync(db, v)
    m = start(sc["mule"][0], 9, "RBI")                                                               # SAR draft
    if m:
        to_sar(m, "Five linked accounts receive many small credits and forward them within hours - mule network."); cases.sync(db, m)
    t = start(sc["tf"][0] if sc["tf"] else None, 6, "RBI")                                           # escalation queue
    if t:
        to_esc(t, "Charity-related donations to conflict-adjacent jurisdictions; MLRO judgement needed.")
    s0 = start(sc["smurf"][0], 5, "RBI")
    if s0:
        to_fiu(s0)
    b = start(sc["smurf_benef"][0] if sc["smurf_benef"] else None, 5, "FIU")
    if b:
        to_fiu(b)
    rp = start(sc["round_pair"][0] if sc["round_pair"] else None, 7, "FIU")
    if rp:
        to_fiu(rp)
    tr = start(sc["traffic"][0] if sc["traffic"] else None, 2, "RBI")                                # triage
    tb = start(sc["tbml"][0] if sc["tbml"] else None, 1, "RBI")
    lena = db.scalar(select(Customer).where(Customer.full_name == "Lena Hoffmann"))
    ln = start(lena, 4, "MANUAL", "Cross-chain movement via bridge to mixer / unlicensed OTC")
    if ln:
        to_fiu(ln)
    fa = start(sc["family_a"][0] if sc["family_a"] else None, 20, "RBI")                               # closed - benign household
    if fa:
        to_fiu(fa)
        do(fa, "mlro.demo", "close", "Linked accounts are family members sharing address and device; transactions explained by household spending. No suspicion.", "NO_SUSPICION")
    # a false-positive closure from a screening alert
    fp = db.scalar(select(Alert).where(Alert.source.in_(["SANCTIONS", "PEP", "ADVERSE_MEDIA"]), Alert.status == "OPEN").order_by(Alert.id))
    if fp:
        try:
            i = cases.open_case(db, "analyst.demo", alert_id=fp.id)
            i.created_at = NOW - timedelta(days=15); made += 1
            do(i, "senior.demo", "close", "Date of birth and nationality differ from the watchlist record; confirmed false positive.", "FALSE_POSITIVE")
        except cases.CaseError:
            pass
    for sr in db.scalars(select(Sar).where(Sar.prepared_by == "senior.demo")):
        sr.prepared_by = "analyst.demo"  # case SARs are drafted by the investigating analyst; the MLRO is the independent approver
    for i in db.scalars(select(Investigation)):
        if i.closed_at and i.closed_at > i.created_at + timedelta(days=60):
            i.closed_at = i.created_at + timedelta(days=11)
        elif i.closed_at is None and i.queue == "CLOSED":
            i.closed_at = NOW
    db.flush()
    return made
