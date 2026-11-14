"""Sample customers covering every risk outcome. Run automatically on first start, or: python -m app.seed [--reset]."""
import sys
from datetime import date

from sqlalchemy import select

from . import audit
from .agents import pipeline
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Customer, Document

Y = date.today().year

SAMPLES = [
    dict(  # 1 - clean LOW
        full_name="Katarzyna Nowak", date_of_birth=date(1988, 4, 12), nationality="Poland", country_of_residence="Poland",
        address="ul. Floriańska 14/3, 31-019 Kraków", occupation="Software Engineer", industry="Information technology",
        source_of_funds="Monthly salary from Acme Software Sp. z o.o. of approx EUR 4,200 net, paid by bank transfer; employed there since 2016.",
        source_of_wealth="Accumulated savings from 10 years of employment as a software engineer (approx EUR 80,000) and a flat in Kraków bought in 2019 with a mortgage.",
        expected_activity="Salary credits of about EUR 4,200 per month, domestic card spend, rent and utilities.",
        annual_income=62000, product="CURRENT_ACCOUNT", channel="FACE_TO_FACE", pep_declared=False,
        status="ACTIVE", onboarded_at=date(Y - 1, 1, 15), last_kyc_review=date(Y - 1, 1, 15),
        docs=[("ID_DOCUMENT", date(Y + 4, 5, 1)), ("PROOF_OF_ADDRESS", None), ("SOF_EVIDENCE", None), ("SOW_EVIDENCE", None)],
    ),
    dict(  # 2 - MEDIUM (UAE resident trader)
        full_name="Rahul Verma", date_of_birth=date(1979, 9, 23), nationality="India", country_of_residence="United Arab Emirates",
        address="Business Bay, Dubai, UAE", occupation="Company Director", industry="Import/export trading",
        source_of_funds="Dividends of around EUR 8,000 per month from Verma General Trading LLC, which I own.",
        source_of_wealth="Founded a trading company in 2014; sold a 20% stake in 2021 for approx EUR 250,000 and reinvested part of the proceeds.",
        expected_activity="Monthly inflows of EUR 8,000 from company dividends; occasional international transfers to family in India.",
        annual_income=96000, product="INTERNATIONAL_WIRES", channel="ONLINE", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 3, 2, 1)), ("PROOF_OF_ADDRESS", None)],
    ),
    dict(  # 3 - declared PEP -> HIGH
        full_name="Aleksandra Nowicka-Wrona", date_of_birth=date(1974, 6, 12), nationality="Poland", country_of_residence="Poland",
        address="ul. Wiejska 4, 00-902 Warszawa", occupation="Member of Parliament", industry="Government",
        source_of_funds="Parliamentary salary of approx EUR 5,500 per month and rental income from one apartment in Gdańsk.",
        source_of_wealth="Career as a lawyer from 1999 to 2015 (partner at a Warsaw law firm), then elected to the Sejm; owns two apartments purchased between 2008 and 2012.",
        expected_activity="Salary credits of EUR 5,500 per month, rental income, mortgage repayments and household spending.",
        annual_income=85000, product="CURRENT_ACCOUNT", channel="FACE_TO_FACE", pep_declared=True, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 5, 3, 3)), ("PROOF_OF_ADDRESS", None), ("SOF_EVIDENCE", None)],
    ),
    dict(  # 4 - strong sanctions match -> PROHIBITED
        full_name="Viktor Kozlov", date_of_birth=date(1968, 3, 14), nationality="Russia", country_of_residence="Cyprus",
        address="Limassol Marina, Limassol, Cyprus", occupation="Executive", industry="Shipping and logistics",
        source_of_funds="Management fees and consultancy income from several companies.",
        source_of_wealth="Long career in the defence-industrial sector; various investments.",
        expected_activity="Incoming wires of EUR 400,000 per month from corporate entities.",
        annual_income=180000, product="PRIVATE_BANKING", channel="INTERMEDIARY", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 2, 7, 7))],
    ),
    dict(  # 5 - prohibited jurisdiction
        full_name="Farid Karimi", date_of_birth=date(1990, 1, 30), nationality="Iran", country_of_residence="Iran",
        address="Valiasr Street, Tehran", occupation="Civil Engineer", industry="Construction",
        source_of_funds="Salary from an engineering firm in Tehran paid monthly in the local currency.",
        source_of_wealth="Savings from employment since 2013 and a family apartment in Tehran.",
        expected_activity="Incoming transfers from abroad of EUR 3,000 per month.",
        annual_income=24000, product="CURRENT_ACCOUNT", channel="ONLINE", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 1, 1, 1))],
    ),
    dict(  # 6 - adverse media + cash intensive + cash SoF
        full_name="Marek Zielinski", date_of_birth=date(1976, 11, 3), nationality="Poland", country_of_residence="Poland",
        address="ul. Szeroka 22, 31-053 Kraków", occupation="Nightclub Owner", industry="Hospitality - nightclubs",
        source_of_funds="Cash takings from my clubs and cash deposits from various events.",
        source_of_wealth="Business.",
        expected_activity="Cash deposits of about EUR 40,000 per month and supplier payments.",
        annual_income=60000, product="CURRENT_ACCOUNT", channel="FACE_TO_FACE", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 3, 9, 9)), ("PROOF_OF_ADDRESS", None)],
    ),
    dict(  # 7 - name collision (weak sanctions + weak media): analyst should clear as false positive
        full_name="Ivan Petrov", date_of_birth=date(1991, 5, 5), nationality="Russia", country_of_residence="Poland",
        address="ul. Grodzka 8/12, 31-006 Kraków", occupation="Warehouse Supervisor", industry="Logistics and warehousing",
        source_of_funds="Salary of EUR 2,300 per month from DHL Supply Chain Poland, employed since 2019.",
        source_of_wealth="Savings from employment in Poland since 2018 (approx EUR 15,000).",
        expected_activity="Salary credits of EUR 2,300 per month and rent payments; occasional transfers to parents.",
        annual_income=33000, product="CURRENT_ACCOUNT", channel="FACE_TO_FACE", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 2, 4, 4)), ("PROOF_OF_ADDRESS", None), ("SOF_EVIDENCE", None)],
    ),
    dict(  # 8 - virtual assets, thin evidence
        full_name="Lena Hoffmann", date_of_birth=date(1992, 8, 17), nationality="Germany", country_of_residence="Germany",
        address="Torstraße 100, 10119 Berlin", occupation="Crypto Trader", industry="Virtual asset trading",
        source_of_funds="Gains from crypto trading.",
        source_of_wealth="Early bitcoin investments in 2016 and crypto mining operations, later reinvested into DeFi protocols.",
        expected_activity="Transfers from crypto exchanges of EUR 60,000 per month.",
        annual_income=210000, product="INTERNATIONAL_WIRES", channel="ONLINE", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 4, 6, 6))],
    ),
    dict(  # 9 - existing customer ripe for periodic review (expired ID, no POA, KYC overdue, diacritics in name)
        full_name="Piotr Wiśniewski", date_of_birth=date(1981, 2, 9), nationality="Poland", country_of_residence="Poland",
        address="ul. Krupnicza 3, 31-123 Kraków", occupation="Restaurant Owner", industry="Restaurant and hospitality",
        source_of_funds="Profits from my restaurant 'Pod Wawelem', approx EUR 3,500 per month after tax.",
        source_of_wealth="Opened the restaurant in 2012 using savings and a bank loan; fully repaid in 2020.",
        expected_activity="Business profit withdrawals of EUR 3,500 per month; supplier payments through the business account.",
        annual_income=48000, product="CURRENT_ACCOUNT", channel="FACE_TO_FACE", pep_declared=False,
        status="ACTIVE", onboarded_at=date(Y - 5, 3, 1), last_kyc_review=date(Y - 4, 3, 1),
        docs=[("ID_DOCUMENT", date(Y - 1, 6, 30))],
    ),
    dict(  # 10 - incomplete onboarding
        full_name="Maria Garcia", date_of_birth=date(1995, 12, 1), nationality="Spain", country_of_residence="Spain",
        address=None, occupation="Consultant", industry="Consulting",
        source_of_funds="", source_of_wealth=None, expected_activity=None, annual_income=None,
        product="CURRENT_ACCOUNT", channel="REMOTE_NO_ID_CHECK", pep_declared=False, status="ONBOARDING",
        docs=[],
    ),
    dict(  # 11 - undeclared (former) PEP in private banking
        full_name="Isabella Marchetti", date_of_birth=date(1966, 10, 5), nationality="Italy", country_of_residence="Switzerland",
        address="Bahnhofstrasse 21, 8001 Zürich", occupation="Board Advisor", industry="Consulting and advisory",
        source_of_funds="Advisory fees of approx EUR 20,000 per month from two corporate boards and dividends from a family vineyard company.",
        source_of_wealth="Long career in public administration, inheritance of a family-owned vineyard in Tuscany (2015) and board remuneration since 2019.",
        expected_activity="Monthly inflows of EUR 20,000 in advisory fees plus annual dividends of about EUR 150,000.",
        annual_income=390000, product="PRIVATE_BANKING", channel="INTERMEDIARY", pep_declared=False, status="ONBOARDING",
        docs=[("ID_DOCUMENT", date(Y + 3, 10, 10)), ("PROOF_OF_ADDRESS", None)],
    ),
]


def seed(db) -> int:
    prior = settings.llm_enabled
    settings.llm_enabled = False  # keep seeding fast, free and deterministic
    try:
        for i, raw in enumerate(SAMPLES, start=1):
            data = dict(raw)
            docs = data.pop("docs")
            c = Customer(customer_ref=f"TMP-{i}", **data)
            db.add(c)
            db.flush()
            c.customer_ref = f"CUST-{c.id:05d}"
            for doc_type, expiry in docs:
                db.add(Document(customer_id=c.id, doc_type=doc_type, expiry_date=expiry, issued_date=date(Y - 1, 1, 1),
                                description="Sample document (seed data)"))
            audit.log(db, actor="seed-script", actor_type=audit.SYSTEM, action="CUSTOMER_CREATED", entity_type="customer",
                      entity_id=c.id, customer_id=c.id, details={"name": c.full_name, "source": "seed"})
            db.commit()
            pipeline.run_full_assessment(db, c, actor="seed-script", trigger="SEED")
    finally:
        settings.llm_enabled = prior
    return len(SAMPLES)


if __name__ == "__main__":
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if session.scalar(select(Customer.id).limit(1)):
            print("Database already contains customers; use --reset to wipe and reseed.")
        else:
            print(f"Seeded {seed(session)} customers.")
