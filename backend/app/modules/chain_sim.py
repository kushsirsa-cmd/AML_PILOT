"""Deterministic simulated blockchain + attribution data (stand-in for a Chainalysis / TRM / Elliptic feed).

All entities and addresses are fictional. Scenarios are built around the seeded customers/corporates so every
risk level and detector can be demonstrated.
"""
import hashlib
from datetime import datetime, timedelta, timezone

PRICES = {"ETH": 3000.0, "BTC": 90000.0, "USDT": 1.0}


def A(name: str, chain: str = "ETH") -> str:
    h = hashlib.sha1(name.encode()).hexdigest()
    return ("bc1q" + h[:38]) if chain == "BTC" else ("0x" + h)


# key -> (category, entity name)
LABELS = {
    "nordex_hot": ("REGULATED_EXCHANGE", "NordEx hot wallet"),
    "alpine_hot": ("REGULATED_EXCHANGE", "AlpineCoin hot wallet"),
    "swirl1": ("MIXER", "SwirlMix pool A"),
    "swirl2": ("MIXER", "SwirlMix pool B"),
    "shadow": ("DARKNET", "ShadowBazaar marketplace"),
    "sanc1": ("SANCTIONED", "Designated entity (SAN-CRY-001, Kozlov network)"),
    "cryptolock": ("RANSOMWARE", "CryptoLockerX payment address"),
    "fakeyield": ("SCAM", "FakeYield Finance (investment scam)"),
    "betchain": ("GAMBLING", "BetChain deposit wallet"),
    "swapdex": ("DEFI", "SwapDex router"),
    "ofex": ("UNREGULATED_EXCHANGE", "OffshoreFX (unlicensed)"),
}

# wallets owned by seeded customers / corporates: key -> spec
WALLETS = {
    "wK": dict(owner=("customer", "Katarzyna Nowak"), label="Personal wallet", vasp=None, self_hosted=True),
    "wL1": dict(owner=("customer", "Lena Hoffmann"), label="Trading wallet", vasp=None, self_hosted=True),
    "wV": dict(owner=("customer", "Viktor Kozlov"), label="Main wallet", vasp=None, self_hosted=True),
    "wM": dict(owner=("customer", "Marek Zielinski"), label="Club takings wallet", vasp=None, self_hosted=True),
    "wC1": dict(owner=("corporate", "Baltic Trade Ventures OÜ"), label="Corporate treasury", vasp=None, self_hosted=True),
    "wH": dict(owner=("corporate", "Helix Digital Assets Ltd"), label="Operational wallet", vasp="NordEx", self_hosted=False),
}


def build(now: datetime | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (labels, wallets, transactions)."""
    now = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    txs: list[dict] = []
    n = [0]

    def tx(frm: str, to: str, eur: float, days_ago: float, hour_offset: float = 0.0, asset: str = "USDT"):
        n[0] += 1
        ts = now - timedelta(days=days_ago) + timedelta(hours=hour_offset)
        h = hashlib.sha256(f"{frm}|{to}|{eur}|{n[0]}".encode()).hexdigest()
        txs.append(dict(
            tx_hash="0x" + h, chain="ETH", from_address=A(frm), to_address=A(to), asset=asset,
            amount=round(eur / PRICES[asset], 6), amount_eur=round(eur, 2), ts=ts,
        ))

    # 1. Katarzyna: clean retail on-ramp from a licensed exchange
    for d, eur in [(80, 250), (70, 400), (55, 300), (40, 500), (25, 350), (10, 600)]:
        tx("nordex_hot", "wK", eur, d, asset="ETH")
    tx("wK", "swapdex", 300, 24, asset="ETH")

    # 2. Lena: mixer exposure two hops back, then a peel chain out
    for d, eur in [(60, 20000), (45, 15000), (30, 12000)]:
        tx("nordex_hot", "wL1", eur, d)
    tx("swirl1", "i1", 30000, 20)
    tx("alpine_hot", "i1", 10000, 21)
    tx("i1", "wL1", 38000, 19, 2)
    tx("wL1", "p1", 60000, 18)
    tx("p1", "p2", 54000, 18, 3); tx("p1", "f1", 6000, 18, 3)
    tx("p2", "p3", 48600, 18, 5); tx("p2", "f2", 5400, 18, 5)
    tx("p3", "p4", 43740, 18, 7); tx("p3", "f3", 4860, 18, 7)
    tx("p4", "betchain", 39366, 17, 2); tx("p4", "f4", 4374, 17, 2)

    # 3. Viktor: direct receipt from a designated entity, cash-out via unlicensed + licensed exchange
    tx("sanc1", "wV", 45000, 15)
    tx("wV", "ofex", 20000, 14)
    tx("wV", "nordex_hot", 22000, 14, 3)

    # 4. Marek: structuring - 12 fan-in deposits just under EUR 10k, two funded by a darknet market
    amounts = [9100, 9450, 9800, 9200, 9650, 9900, 9300, 9700, 9500, 9250, 9850, 9400]
    for i, eur in enumerate(amounts, start=1):
        tx(f"u{i}", "wM", eur, 13 - i * 0.9, 1 + i % 5)
    tx("shadow", "u3", 9800, 14.5)
    tx("shadow", "u7", 9700, 13.5)
    tx("wM", "alpine_hot", 60000, 1)
    tx("wM", "ofex", 40000, 1, 2)

    # 5. Baltic Trade Ventures: rapid pass-through of 98% within hours to fresh self-hosted wallets
    for i in range(1, 7):
        tx(f"c_src{i}", "wC1", 20000, 8 - i * 0.3, 1)
    tx("betchain", "wC1", 15000, 7)
    tx("wC1", "c_out1", 45000, 6, 2); tx("wC1", "c_out2", 45000, 6, 3); tx("wC1", "c_out3", 40000, 5.5, 1)
    tx("c_out1", "ofex", 44000, 5.9)

    # 6. Helix Digital Assets: ordinary custodial flows
    for d, eur in [(70, 80000), (50, 60000), (30, 75000), (12, 50000)]:
        tx("nordex_hot", "wH", eur, d)
    for d, eur in [(65, 30000), (45, 20000), (20, 40000)]:
        tx("wH", "alpine_hot", eur, d)
    tx("wH", "swapdex", 15000, 33)

    # 7. Background criminal activity so labelled addresses have a history (and 'ad-hoc' screening demos work)
    for i in range(1, 6):
        tx(f"victim{i}", "cryptolock", 1500 * i, 40 - i)
        tx(f"victim{i}", "fakeyield", 900 * i, 35 - i)
    tx("cryptolock", "swirl2", 7000, 20)
    tx("fakeyield", "swirl2", 3500, 18)
    tx("swirl2", "ransom_cashout", 9000, 17)
    tx("ransom_cashout", "ofex", 8800, 16)

    labels = [
        dict(address=A(k), chain="ETH", category=cat, entity_name=name, source="SIMULATED-ATTRIBUTION")
        for k, (cat, name) in LABELS.items()
    ]
    wallets = [
        dict(key=k, address=A(k), chain="ETH", label=v["label"], owner_type=v["owner"][0], owner_name=v["owner"][1],
             hosted_by_vasp=v["vasp"], self_hosted=v["self_hosted"])
        for k, v in WALLETS.items()
    ]
    return labels, wallets, txs
