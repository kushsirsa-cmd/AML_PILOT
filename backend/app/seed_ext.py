"""Phase-2 sample data: corporates + ownership structures, simulated chain, wallets, travel-rule transfers, alerts, SAR, QA, report.

Runs automatically after the customer seed (see main.py), or: python -m app.seed_ext
"""
from datetime import date, timedelta

from sqlalchemy import select

from . import audit
from .config import settings
from .db import Base, SessionLocal, engine
from .models import AddressLabel, Alert, ChainTx, Corporate, Customer, Wallet
from .modules import alerts as alertsvc
from .modules import chain_sim, kyb, qa, reporting, sar as sarsvc, travel_rule, wallets as wsvc

Y = date.today().year


def P(key, name, country, dob=None, role=None, verified=False, **kw):
    return dict(key=key, name=name, node_type="PERSON", country=country, dob=dob, role=role, id_verified=verified, **kw)


def E(key, name, country, **kw):
    return dict(key=key, name=name, node_type="ENTITY", country=country, **kw)


def O(owner, owned, pct, ctl="SHARES"):
    return dict(owner=owner, owned=owned, percentage=pct, control_type=ctl)


CORPORATES = [
    dict(  # 1 clean
        corp=dict(legal_name="Nordic Software AB", registration_number="556123-4567", country_of_incorporation="Sweden", entity_type="LIMITED_COMPANY",
                  industry="Software development", incorporation_date=date(2015, 3, 2), registered_address="Kungsgatan 12, Stockholm",
                  operating_countries="Sweden, Germany, Poland", annual_turnover=2400000, employees=18,
                  expected_activity="Customer receipts from SaaS subscriptions (EU), payroll and supplier payments.", status="ACTIVE"),
        nodes=[P("anna", "Anna Lindqvist", "Sweden", "1980-05-11", "Director / CEO", True), P("erik", "Erik Berg", "Sweden", "1978-09-02", "Director", True)],
        edges=[O("anna", "ROOT", 60), O("erik", "ROOT", 40)]),
    dict(  # 2 prohibited: sanctioned UBO through BVI trust + Seychelles holding, nominee, bearer shares
        corp=dict(legal_name="Baltic Trade Ventures OÜ", registration_number="14876543", country_of_incorporation="Estonia", entity_type="LIMITED_COMPANY",
                  industry="Commodities trading", incorporation_date=date(Y - 1, 6, 1), registered_address="Harju maakond, Tallinn (virtual office)",
                  operating_countries="Estonia, Russia, Cyprus, United Arab Emirates", annual_turnover=18000000, employees=2,
                  expected_activity="Cross-border commodity trade settlements, partly in stablecoins.", has_bearer_shares=True, nominee_directors=True,
                  status="ONBOARDING"),
        nodes=[E("sey", "Seychelles Holdings Ltd", "Seychelles"), E("cedar", "Cedar Trust", "British Virgin Islands", is_trust=True),
               P("vk", "Viktor Kozlov", "Russia", "1968-03-14", "Beneficial owner"), P("nom", "Nominee Services Ltd (nominee director)", "Cyprus", None, "Director", False, is_nominee=True),
               P("anon", "Settlor of Cedar Trust (undisclosed)", None, None, "Settlor", False)],
        edges=[O("sey", "ROOT", 100), O("cedar", "sey", 70), O("vk", "sey", 30), O("anon", "cedar", 100, "SETTLOR")]),
    dict(  # 3 domestic, verified
        corp=dict(legal_name="Kraków Logistics Sp. z o.o.", registration_number="0000781234", country_of_incorporation="Poland", entity_type="LIMITED_COMPANY",
                  industry="Freight and logistics", incorporation_date=date(2012, 9, 14), registered_address="ul. Wielicka 50, Kraków",
                  operating_countries="Poland, Czechia, Slovakia", annual_turnover=5200000, employees=46,
                  expected_activity="Freight invoicing, fuel and driver payments, leasing instalments.", status="ACTIVE"),
        nodes=[P("marek", "Marek Zielinski", "Poland", "1976-11-03", "Director", True), P("ola", "Ola Zielinska", "Poland", "1979-02-21", "Shareholder", True)],
        edges=[O("marek", "ROOT", 55), O("ola", "ROOT", 20)]),  # 25% unaccounted -> flagged
    dict(  # 4 crypto firm, circular ownership, unverified UBO
        corp=dict(legal_name="Helix Digital Assets Ltd", registration_number="HE443322", country_of_incorporation="Cyprus", entity_type="LIMITED_COMPANY",
                  industry="Cryptocurrency / virtual asset services", incorporation_date=date(Y - 2, 2, 10), registered_address="Limassol, Cyprus",
                  operating_countries="Cyprus, Malta, United Kingdom", annual_turnover=3000000, employees=7,
                  expected_activity="OTC crypto trading, stablecoin settlement for institutional clients.", status="ONBOARDING"),
        nodes=[E("hold", "Helix Holdings Ltd", "Malta"), E("hxc", "HX Capital Partners", "Cyprus"), P("dm", "Dimitris Markou", "Cyprus", "1985-07-19", "Founder", False)],
        edges=[O("hold", "ROOT", 80), O("dm", "hold", 40), O("hxc", "hold", 60), O("hold", "hxc", 50), O("dm", "ROOT", 20)]),
    dict(  # 5 incomplete structure
        corp=dict(legal_name="Alpine Consulting GmbH", registration_number="CHE-123.456.789", country_of_incorporation="Switzerland", entity_type="LIMITED_COMPANY",
                  industry="Management consulting", incorporation_date=date(2018, 4, 5), registered_address="Bahnhofstrasse 1, Zürich",
                  operating_countries="Switzerland, Germany, Austria", annual_turnover=900000, employees=6,
                  expected_activity="Consulting fees from EU corporate clients, salaries and rent.", status="ONBOARDING"),
        nodes=[P("hs", "Hans Schmid", "Switzerland", "1971-01-30", "Managing director", True), P("cb", "Claire Bonnet", "France", "1975-10-08", "Shareholder", True)],
        edges=[O("hs", "ROOT", 40), O("cb", "ROOT", 30)]),
]

TRANSFERS = [
    # fully compliant inbound from licensed VASP
    dict(direction="IN", amount_eur=2500, asset="USDT", counterparty_vasp="NordEx", customer="Lena Hoffmann",
         originator=dict(name="Jonas Weber", account=chain_sim.A("nordex_hot"), address="Berlin, Germany", dob="1990-02-01"),
         beneficiary=dict(name="Lena Hoffmann", account=chain_sim.A("wL1"))),
    # below threshold -> data not mandatory
    dict(direction="OUT", amount_eur=400, asset="ETH", counterparty_vasp="AlpineCoin", customer="Katarzyna Nowak",
         originator=dict(name="Katarzyna Nowak", account=chain_sim.A("wK")), beneficiary=dict(name="A. Keller", account=chain_sim.A("alpine_hot"))),
    # unhosted wallet, missing beneficiary info, no ownership proof
    dict(direction="OUT", amount_eur=6500, asset="USDT", self_hosted=True, ownership_proof=False, customer="Marek Zielinski",
         originator=dict(name="Marek Zielinski", account=chain_sim.A("wM"), address="ul. Długa 5, Kraków"), beneficiary=dict(account=chain_sim.A("unknown_selfhosted"))),
    # sanctioned originator
    dict(direction="IN", amount_eur=48000, asset="USDT", counterparty_vasp="NordEx", customer="Viktor Kozlov",
         originator=dict(name="Viktor Kozlov", account=chain_sim.A("sanc1"), address="Limassol, Cyprus", dob="1968-03-14"),
         beneficiary=dict(name="Viktor Kozlov", account=chain_sim.A("wV"))),
    # unlicensed counterparty VASP
    dict(direction="OUT", amount_eur=12000, asset="USDT", counterparty_vasp="OffshoreFX", customer="Viktor Kozlov",
         originator=dict(name="Viktor Kozlov", account=chain_sim.A("wV"), address="Limassol, Cyprus"),
         beneficiary=dict(name="Unknown", account=chain_sim.A("ofex"), address="n/a")),
]

WEAK_DECISIONS = [  # (customer name, action, details) written as an analyst so QA has something to find
    ("Aleksandra Nowicka-Wrona", "REVIEW_DECISION", dict(decision="APPROVE", note="ok", analyst_note="ok")),
    ("Ivan Petrov", "SCREENING_HIT_DISPOSITION", dict(disposition="FALSE_POSITIVE", note="no match")),
]


def seed_ext(db) -> dict:
    prior = settings.llm_enabled
    settings.llm_enabled = False
    try:
        cust = {c.full_name: c for c in db.scalars(select(Customer))}

        # 1. corporates + KYB
        corps: dict[str, Corporate] = {}
        for spec in CORPORATES:
            c = Corporate(corp_ref="TMP", **spec["corp"])
            db.add(c)
            db.flush()
            c.corp_ref = f"CORP-{c.id:05d}"
            audit.log(db, actor="seed-script", actor_type=audit.SYSTEM, action="CORPORATE_CREATED", entity_type="corporate", entity_id=c.id, details={"name": c.legal_name})
            kyb.replace_structure(db, c, spec["nodes"], spec["edges"])
            corps[c.legal_name] = c
            db.commit()

        # 2. chain + labels + wallets
        labels, wallets, txs = chain_sim.build()
        for l in labels:
            db.add(AddressLabel(**l))
        for t in txs:
            db.add(ChainTx(**t))
        ws: list[Wallet] = []
        for w in wallets:
            kind, name = w["owner_type"], w["owner_name"]
            owner = cust.get(name) if kind == "customer" else corps.get(name)
            if not owner:
                continue
            row = Wallet(address=w["address"], chain=w["chain"], label=w["label"], hosted_by_vasp=w["hosted_by_vasp"], self_hosted=w["self_hosted"],
                         customer_id=owner.id if kind == "customer" else None, corporate_id=owner.id if kind == "corporate" else None)
            db.add(row)
            ws.append(row)
        db.commit()
        for w in ws:
            wsvc.screen_wallet(db, w, actor="seed-script")
        db.commit()
        for cid in {w.customer_id for w in ws if w.customer_id}:
            wsvc.refresh_customer_risk(db, cid, "seed-script")
        db.commit()

        # 3. KYB reviews (after wallets so crypto alerts exist independently)
        for c in corps.values():
            kyb.run(db, c, actor="seed-script")
        db.commit()

        # 4. travel rule
        for t in TRANSFERS:
            p = {k: v for k, v in t.items() if k != "customer"}
            if t.get("customer") and t["customer"] in cust:
                p["customer_id"] = cust[t["customer"]].id
            travel_rule.check_and_store(db, p, actor="seed-script")
        db.commit()

        # 5. MLRO escalation + SAR draft for Viktor
        v = cust.get("Viktor Kozlov")
        sar_ref = None
        if v:
            a = db.scalar(select(Alert).where(Alert.customer_id == v.id, Alert.source == "CRYPTO").order_by(Alert.id))
            if not a:
                a = alertsvc.raise_alert(db, source="CUSTOMER_RISK", entity_type="customer", entity_id=v.id, customer_id=v.id, severity="CRITICAL",
                                         title="Sanctions-linked customer with direct sanctioned wallet exposure", description="Seeded alert", details={})
            from datetime import datetime, timezone
            a.status, a.escalated_at, a.assigned_to = "ESCALATED_MLRO", datetime.now(timezone.utc), "analyst.demo"
            a.resolution = "Direct receipt from designated address; customer is a sanctions match. Escalating for SAR decision."
            audit.log(db, actor="analyst.demo", actor_type=audit.USER, action="ALERT_ACTION", entity_type="alert", entity_id=a.id, customer_id=v.id,
                      details=dict(action="ESCALATE", note=a.resolution, status_to="ESCALATED_MLRO", priority=a.severity))
            s = sarsvc.generate(db, "customer", v.id, actor="analyst.demo", alert_id=a.id)
            s.status, s.submitted_at = "PENDING_MLRO", datetime.now(timezone.utc)
            a.status, a.sar_id = "SAR_DRAFTED", s.id
            a.status = "ESCALATED_MLRO"  # stays in the MLRO queue until a decision is recorded
            sar_ref = s.reference
            db.commit()

        # 6. weak analyst decisions for QA demo, then sample
        for name, action, details in WEAK_DECISIONS:
            c = cust.get(name)
            if c:
                audit.log(db, actor="analyst.demo", actor_type=audit.USER, action=action, entity_type="customer", entity_id=c.id, customer_id=c.id, details=details)
        db.commit()
        sampled = qa.sample(db, days=30, low_risk_rate=1.0, actor="seed-script")
        db.commit()

        # 7. regulatory report draft
        rpt = reporting.generate(db, "CRYPTO_ACTIVITY", date.today() - timedelta(days=90), date.today(), actor="analyst.demo")
        db.commit()
        return dict(corporates=len(corps), wallets=len(ws), transfers=len(TRANSFERS), sar=sar_ref, qa_items=len(sampled), report=rpt.id)
    finally:
        settings.llm_enabled = prior


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.scalar(select(Corporate.id).limit(1)):
            print("Corporates already present; skipping.")
        else:
            print("Seeded:", seed_ext(session))
