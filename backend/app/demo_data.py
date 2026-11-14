"""Demo dataset generator: 100 customers, 50 business entities, 500 transactions, alerts, reviews, SARs, QA, reports.

Deterministic (fixed RNG seed) so every start-up / reset produces the same story. Runs with Claude disabled.
Entry points: `seed_users`, `extend` (called after app.seed and app.seed_ext), `reset_and_seed` (admin 'reset demo' button).
"""
import random
from datetime import date, datetime, timedelta, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from . import audit
from .agents import event_driven, pipeline
from .agents import periodic
from .agents.risk import next_review_date
from .auth import DEMO_USERS
from .config import settings
from .models import Alert, AuditLog, Corporate, Customer, Document, Review, Sar, Transaction, User
from .modules import kyb, qa, reporting
from .modules import sar as sarsvc
from .modules.txmon import monitor

TODAY = date.today()
NOW = datetime.now(timezone.utc)

PL_M = ["Piotr", "Tomasz", "Marcin", "Michał", "Paweł", "Krzysztof", "Jakub", "Adam", "Łukasz", "Mateusz", "Rafał", "Grzegorz", "Wojciech", "Dariusz", "Kamil", "Bartosz"]
PL_F = ["Anna", "Maria", "Katarzyna", "Małgorzata", "Agnieszka", "Barbara", "Ewa", "Joanna", "Magdalena", "Monika", "Natalia", "Karolina", "Zofia", "Dorota", "Weronika"]
PL_LAST_M = ["Kowalski", "Nowak", "Wiśniewski", "Wójcik", "Kamiński", "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", "Jankowski", "Mazur", "Krawczyk", "Piotrowski", "Grabowski", "Pawlak", "Michalski", "Król", "Wieczorek"]
INTL = {  # country: (male firsts, female firsts, surnames)
    "Germany": (["Lukas", "Jonas", "Felix", "Maximilian"], ["Sophie", "Lea", "Hannah", "Marie"], ["Müller", "Schneider", "Fischer", "Becker", "Hoffmann", "Wagner"]),
    "Spain": (["Javier", "Carlos", "Diego", "Pablo"], ["Lucía", "Carmen", "Elena", "Paula"], ["García", "Martínez", "López", "Sánchez", "Romero"]),
    "Italy": (["Marco", "Luca", "Matteo", "Giovanni"], ["Giulia", "Chiara", "Francesca", "Sara"], ["Rossi", "Bianchi", "Ferrari", "Esposito", "Conti"]),
    "France": (["Louis", "Hugo", "Jules", "Nicolas"], ["Camille", "Léa", "Manon", "Julie"], ["Martin", "Bernard", "Dubois", "Moreau", "Laurent"]),
    "United Kingdom": (["Oliver", "George", "Harry", "James"], ["Amelia", "Isla", "Emily", "Grace"], ["Smith", "Jones", "Taylor", "Brown", "Wilson"]),
    "India": (["Arjun", "Vikram", "Rohan", "Sanjay"], ["Priya", "Ananya", "Neha", "Kavya"], ["Sharma", "Patel", "Iyer", "Gupta", "Reddy"]),
    "United Arab Emirates": (["Omar", "Khalid", "Yusuf", "Hamad"], ["Fatima", "Mariam", "Aisha", "Noura"], ["Al-Nahyan", "Al-Suwaidi", "Al-Hashimi", "Al-Ketbi"]),
    "Turkey": (["Mehmet", "Emre", "Burak", "Can"], ["Elif", "Zeynep", "Ayşe", "Selin"], ["Yılmaz", "Kaya", "Demir", "Çelik"]),
    "Nigeria": (["Chinedu", "Tunde", "Emeka", "Ibrahim"], ["Ngozi", "Funke", "Amara", "Aisha"], ["Okafor", "Adeyemi", "Balogun", "Eze"]),
    "Pakistan": (["Ahmed", "Bilal", "Usman", "Hamza"], ["Ayesha", "Sana", "Hira", "Maryam"], ["Khan", "Malik", "Qureshi", "Siddiqui"]),
    "Lebanon": (["Karim", "Fadi", "Rami", "Elias"], ["Nour", "Rima", "Maya", "Layal"], ["Khoury", "Nasser", "Haddad", "Gemayel"]),
    "Venezuela": (["Andrés", "Luis", "Rafael", "Gabriel"], ["Valentina", "Daniela", "Mariana", "Isabel"], ["Rodríguez", "Pérez", "Gómez", "Torres"]),
    "Ukraine": (["Andrii", "Oleksandr", "Taras", "Bohdan"], ["Olena", "Iryna", "Kateryna", "Oksana"], ["Shevchenko", "Bondarenko", "Kovalenko", "Melnyk"]),
    "Romania": (["Andrei", "Mihai", "Stefan", "Radu"], ["Ioana", "Elena", "Andreea", "Cristina"], ["Popescu", "Ionescu", "Dumitru", "Stan"]),
    "Brazil": (["Gabriel", "Lucas", "Rafael", "Thiago"], ["Beatriz", "Juliana", "Camila", "Larissa"], ["Silva", "Santos", "Oliveira", "Souza"]),
    "Netherlands": (["Daan", "Sem", "Bram", "Joost"], ["Emma", "Sanne", "Lotte", "Femke"], ["de Vries", "Jansen", "van Dijk", "Bakker"]),
}
CITY = {"Poland": ["Warszawa", "Kraków", "Wrocław", "Gdańsk", "Poznań", "Łódź", "Katowice"], "Germany": ["Berlin", "Munich", "Hamburg"], "Spain": ["Madrid", "Valencia"],
        "Italy": ["Milan", "Rome"], "France": ["Paris", "Lyon"], "United Kingdom": ["London", "Manchester"], "India": ["Mumbai", "Bengaluru"], "United Arab Emirates": ["Dubai", "Abu Dhabi"],
        "Turkey": ["Istanbul", "Ankara"], "Nigeria": ["Lagos", "Abuja"], "Pakistan": ["Karachi", "Lahore"], "Lebanon": ["Beirut"], "Venezuela": ["Caracas"], "Ukraine": ["Kyiv", "Lviv"],
        "Romania": ["Bucharest"], "Brazil": ["São Paulo"], "Netherlands": ["Amsterdam"], "Cyprus": ["Limassol"], "Serbia": ["Belgrade"], "Portugal": ["Lisbon"], "Colombia": ["Bogotá"]}
STREETS = ["ul. Długa", "ul. Krótka", "ul. Słoneczna", "ul. Lipowa", "ul. Polna", "ul. Kościuszki", "ul. Mickiewicza", "Hauptstraße", "Calle Mayor", "Main Street", "Rue de la Paix", "Via Roma"]
EMPLOYERS = ["Allegro", "mBank", "PKO BP", "Orlen", "Accenture Poland", "Capgemini", "Siemens", "Lidl Polska", "InPost", "Comarch", "Asseco", "Deloitte", "Bosch", "Philips", "Tauron"]

# occupation, industry, (income low, high), kind
JOBS = [
    ("Software Engineer", "Information technology", (45000, 110000), "salary"), ("Nurse", "Healthcare", (24000, 38000), "salary"), ("Teacher", "Education", (22000, 34000), "salary"),
    ("Accountant", "Accounting and finance", (30000, 55000), "salary"), ("Sales Manager", "Retail and wholesale", (36000, 70000), "salary"), ("Electrician", "Construction", (26000, 45000), "salary"),
    ("Marketing Manager", "Marketing and advertising", (40000, 75000), "salary"), ("Mechanical Engineer", "Manufacturing", (38000, 72000), "salary"), ("Physician", "Healthcare", (55000, 120000), "salary"),
    ("Pharmacist", "Healthcare", (32000, 52000), "salary"), ("Truck Driver", "Transport and logistics", (26000, 40000), "salary"), ("Bank Clerk", "Banking", (28000, 45000), "salary"),
    ("Restaurant Owner", "Hospitality", (45000, 90000), "business"), ("Retail Store Owner", "Retail and wholesale", (40000, 85000), "business"), ("Freelance Consultant", "Management consulting", (50000, 120000), "business"),
    ("Real Estate Agent", "Real estate", (40000, 140000), "business"), ("Import/Export Trader", "Import/export trading", (60000, 180000), "business"), ("Architect", "Architecture", (45000, 95000), "business"),
]
RISKY_JOBS = [
    ("Jeweller", "Precious metals and jewellery", (50000, 110000)), ("Casino Operator", "Gambling and casinos", (80000, 220000)), ("Used Car Dealer", "Automotive trading", (50000, 130000)),
    ("Crypto Trader", "Virtual asset trading", (70000, 250000)), ("Art Dealer", "Art and antiques", (60000, 200000)), ("Currency Exchange Owner", "Money services business", (60000, 150000)),
]
VAGUE_SOF = ["Business income.", "Savings.", "Family support and gifts.", "Investments and other income.", "Various sources.", "Income from my activities."]
PEP_ROLES = [("Voivodeship Councillor", "Government"), ("Deputy Mayor", "Government"), ("Board Member, state-owned energy company", "Energy"), ("Appellate Court Judge", "Judiciary"),
             ("Colonel, Ministry of Defence", "Defence"), ("Senior Ministry Official", "Government")]

UNDECLARED_PEPS = [("Maria Fernanda Castellanos", date(1981, 3, 3), "Colombia", "Spain"), ("Rashid Bin Saeed Al-Falasi", date(1970, 9, 17), "United Arab Emirates", "United Arab Emirates"),
                   ("Joao Pedro Carvalho", date(1963, 12, 9), "Portugal", "Portugal")]
SANCTION_HITS = [("Dmitri Volkov", date(1985, 9, 9), "Russia", "Cyprus"), ("Elena Sidorova", date(1979, 2, 11), "Russia", "Serbia")]
NAME_COLLISIONS = [("Hassan Rashidi", date(1992, 1, 14), "Jordan", "Poland"), ("Oleg Strakhov", date(1990, 6, 6), "Poland", "Poland"), ("Daniel Weber", date(1990, 11, 20), "Germany", "Germany"),
                   ("Nasser Almansoori", date(1987, 2, 2), "United Arab Emirates", "United Arab Emirates")]
ADVERSE = [("Faisal Mahmood", "Pakistan", "Pakistan"), ("Carlos Eduardo Mendes", "Brazil", "Brazil"), ("Stefan Richter", "Germany", "Germany"), ("Layla Haddad", "Lebanon", "Lebanon")]

SECTORS = [("Software", "Software development"), ("Logistics", "Freight and logistics"), ("Foods", "Food production"), ("Construction", "Construction"), ("Retail", "Retail and wholesale"),
           ("Consulting", "Management consulting"), ("Medical", "Healthcare services"), ("Trading", "Import/export trading"), ("Properties", "Real estate"), ("Energy", "Renewable energy"),
           ("Hospitality", "Hospitality"), ("Motors", "Automotive trading"), ("Digital Assets", "Cryptocurrency / virtual asset services"), ("Gaming", "Gambling and casinos"),
           ("Metals", "Precious metals and jewellery"), ("Exchange", "Money services business"), ("Media", "Media and publishing"), ("Engineering", "Manufacturing")]
SUFFIX = {"Poland": "Sp. z o.o.", "Germany": "GmbH", "Estonia": "OÜ", "United Kingdom": "Ltd", "Cyprus": "Ltd", "Sweden": "AB", "Netherlands": "B.V.", "Switzerland": "AG",
          "United Arab Emirates": "FZE", "Malta": "Ltd", "Luxembourg": "S.A.", "Czechia": "s.r.o.", "Lithuania": "UAB", "Ireland": "Ltd"}
OFFSHORE = ["British Virgin Islands", "Seychelles", "Panama", "Cayman Islands"]


def seed_users(db: Session) -> None:
    for username, name, role, email in DEMO_USERS:
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, full_name=name, role=role, email=email))
    db.commit()


def _fem(s: str) -> str:
    return s[:-1] + "a" if s.endswith(("ski", "cki")) else s


class Gen:
    def __init__(self):
        self.rng = random.Random(2026)
        self.used: set[str] = set()

    def person(self, country: str | None = None) -> tuple[str, str, str]:
        """(full name, nationality, gender)"""
        r = self.rng
        for _ in range(50):
            g = r.choice("MF")
            if country in (None, "Poland"):
                last = r.choice(PL_LAST_M)
                name = f"{r.choice(PL_M)} {last}" if g == "M" else f"{r.choice(PL_F)} {_fem(last)}"
                nat = "Poland"
            else:
                m, f, l = INTL[country]
                name = f"{r.choice(m if g == 'M' else f)} {r.choice(l)}"
                nat = country
            if name not in self.used:
                self.used.add(name)
                return name, nat, g
        raise RuntimeError("name pool exhausted")

    def dob(self, lo=1950, hi=2001) -> date:
        return date(self.rng.randint(lo, hi), self.rng.randint(1, 12), self.rng.randint(1, 28))

    def address(self, country: str) -> str:
        r = self.rng
        return f"{r.choice(STREETS)} {r.randint(1, 120)}/{r.randint(1, 60)}, {r.choice(CITY.get(country, [country]))}"


def _salary_texts(g: Gen, job, income):
    r = g.rng
    m = int(income / 12 * 0.78 / 50) * 50
    emp = r.choice(EMPLOYERS)
    yr = TODAY.year - r.randint(2, 15)
    return (f"Monthly salary from {emp} of approx EUR {m:,} net, paid by bank transfer; employed there since {yr}.",
            f"Accumulated savings from {TODAY.year - yr + r.randint(0, 3)} years of employment as {('a ' if job[0][0] not in 'AEIOU' else 'an ') + job[0].lower()} (approx EUR {int(income * r.uniform(0.4, 1.4) / 500) * 500:,}) and a modest family inheritance.",
            f"Salary credits of about EUR {m:,} per month, domestic card spend, rent or mortgage and utilities.", emp)


def _business_texts(g: Gen, job, income):
    r = g.rng
    m = int(income / 12 / 100) * 100
    yr = TODAY.year - r.randint(3, 14)
    return (f"Drawings and dividends of about EUR {m:,} per month from my own {job[1].lower()} business, registered in {yr}; annual accounts filed with the tax office.",
            f"Built the business since {yr}; sold a small stake in a previous venture in {yr - 2} for approx EUR {int(income * r.uniform(0.8, 2.5) / 1000) * 1000:,}.",
            f"Monthly business drawings of about EUR {m:,}, supplier payments and personal spend.", None)


def _customer_dict(g: Gen, i: int, kind: str) -> dict:
    r = g.rng
    country = None if r.random() < 0.55 else r.choice(["Germany", "Spain", "Italy", "France", "United Kingdom", "Netherlands", "Romania", "Ukraine"])
    name, nat, _ = g.person(country)
    residence = nat if r.random() < 0.85 else "Poland"
    d = dict(full_name=name, nationality=nat, country_of_residence=residence, date_of_birth=g.dob(), address=g.address(residence), pep_declared=False,
             product=r.choice(["CURRENT_ACCOUNT", "CURRENT_ACCOUNT", "SAVINGS", "CREDIT_CARD", "MORTGAGE", "INVESTMENT"]), channel=r.choice(["FACE_TO_FACE", "ONLINE", "ONLINE", "INTERMEDIARY"]))
    job = r.choice(JOBS)
    income = r.randint(*job[2]) // 500 * 500
    sof, sow, act, _e = (_salary_texts if job[3] == "salary" else _business_texts)(g, job, income)
    d.update(occupation=job[0], industry=job[1], annual_income=income, source_of_funds=sof, source_of_wealth=sow, expected_activity=act)
    return d


def _docs(g: Gen, strong: bool, expired: bool = False, partial: bool = False):
    r = g.rng
    docs = [("ID_DOCUMENT", TODAY - timedelta(days=r.randint(20, 200)) if expired else TODAY + timedelta(days=r.randint(200, 2000)))]
    if not partial:
        docs.append(("PROOF_OF_ADDRESS", None))
    if strong:
        docs += [("SOF_EVIDENCE", None), ("SOW_EVIDENCE", None)]
    return docs


def build_customers(g: Gen, n: int) -> list[dict]:
    r = g.rng
    out: list[dict] = []

    def add(d, strong=True, **kw):
        d["docs"] = _docs(g, strong, kw.get("expired", False), kw.get("partial", False))
        out.append(d)

    for _ in range(n):  # base population first, specials replace the tail
        d = _customer_dict(g, len(out), "std")
        add(d, strong=r.random() < 0.6, expired=r.random() < 0.05, partial=r.random() < 0.06)
    out = out[: n - 32]
    specials: list[dict] = []
    for nm, dob, nat, res in UNDECLARED_PEPS:
        d = _customer_dict(g, 0, "pep"); d.update(full_name=nm, date_of_birth=dob, nationality=nat, country_of_residence=res, address=g.address(res), annual_income=r.choice([90000, 140000, 200000]))
        d["source_of_funds"] = "Consulting and advisory fees plus rental income; salary from a previous public-sector role has ended."
        specials.append(d)
    for nm, dob, nat, res in SANCTION_HITS:
        d = _customer_dict(g, 0, "san"); d.update(full_name=nm, date_of_birth=dob, nationality=nat, country_of_residence=res, address=g.address(res), occupation="Business Consultant", industry="Management consulting", annual_income=95000)
        specials.append(d)
    for nm, dob, nat, res in NAME_COLLISIONS:
        d = _customer_dict(g, 0, "col"); d.update(full_name=nm, date_of_birth=dob, nationality=nat, country_of_residence=res, address=g.address(res))
        specials.append(d)
    for nm, nat, res in ADVERSE:
        d = _customer_dict(g, 0, "adv"); d.update(full_name=nm, nationality=nat, country_of_residence=res, address=g.address(res), occupation="Company Director", industry="Import/export trading", annual_income=120000)
        specials.append(d)
    for role, ind in PEP_ROLES:  # declared PEPs
        nm, nat, _ = g.person("Poland")
        d = _customer_dict(g, 0, "pep"); d.update(full_name=nm, nationality="Poland", country_of_residence="Poland", address=g.address("Poland"), occupation=role, industry=ind, pep_declared=True, annual_income=r.choice([64000, 78000, 92000]))
        d["source_of_funds"] = f"Salary of approx EUR {d['annual_income'] // 12:,} per month from public office; no other regular income."
        specials.append(d)
    for country in ["Nigeria", "Lebanon", "Pakistan", "Venezuela", "Turkey", "United Arab Emirates"]:  # high-risk geography
        nm, nat, _ = g.person(country)
        d = _customer_dict(g, 0, "geo"); d.update(full_name=nm, nationality=nat, country_of_residence=nat, address=g.address(nat), occupation="Import/Export Trader", industry="Import/export trading", annual_income=r.randint(60, 150) * 1000, product="INTERNATIONAL_WIRES")
        specials.append(d)
    for country in ["Iran", "Syria"]:
        nm = {"Iran": "Reza Hosseini", "Syria": "Samir Haddad"}[country]
        d = _customer_dict(g, 0, "prohib"); d.update(full_name=nm, nationality=country, country_of_residence=country, address=f"Central District, {country}", annual_income=48000)
        specials.append(d)
    for occ, ind, (lo, hi) in RISKY_JOBS[:5]:
        nm, nat, _ = g.person(None)
        d = _customer_dict(g, 0, "ind"); d.update(full_name=nm, nationality=nat, country_of_residence="Poland", occupation=occ, industry=ind, annual_income=r.randint(lo, hi) // 1000 * 1000, channel="ONLINE")
        d["source_of_funds"] = r.choice(VAGUE_SOF)
        d["source_of_wealth"] = r.choice(VAGUE_SOF)
        specials.append(d)
    for s in specials:
        add(s, strong=False, partial=r.random() < 0.3)
    # vague SoF on a few base customers
    for d in r.sample(out[: n - 32], 5):
        d["source_of_funds"], d["source_of_wealth"] = r.choice(VAGUE_SOF), r.choice(VAGUE_SOF)
    return out[: n]


def create_customers(db: Session, specs: list[dict], start_index: int) -> list[Customer]:
    created = []
    for i, raw in enumerate(specs, start=start_index):
        data = dict(raw)
        docs = data.pop("docs")
        c = Customer(customer_ref=f"TMP-{i}", status="ONBOARDING", **data)
        db.add(c)
        db.flush()
        c.customer_ref = f"CUST-{c.id:05d}"
        for t, exp in docs:
            db.add(Document(customer_id=c.id, doc_type=t, expiry_date=exp, issued_date=TODAY - timedelta(days=400), description="Demo document (seed data)"))
        audit.log(db, actor="seed-script", actor_type=audit.SYSTEM, action="CUSTOMER_CREATED", entity_type="customer", entity_id=c.id, customer_id=c.id, details={"name": c.full_name, "source": "demo-data"})
        db.commit()
        pipeline.run_full_assessment(db, c, actor="seed-script", trigger="SEED")
        created.append(c)
    return created


def decide_statuses(db: Session, g: Gen, customers: list[Customer]) -> None:
    """Give customers a realistic lifecycle state + analyst decisions in the audit trail."""
    r = g.rng
    analysts = ["analyst.demo", "analyst.demo", "analyst.demo", "senior.demo"]
    for c in customers:
        rating = c.risk_rating or "MEDIUM"
        roll = r.random()
        if rating == "PROHIBITED":
            c.status = "REJECTED" if roll < 0.5 else "UNDER_REVIEW"
            who, decision = ("mlro.demo", "REJECT") if c.status == "REJECTED" else (None, None)
        elif rating == "HIGH":
            c.status = "ACTIVE" if roll < 0.4 else "UNDER_REVIEW" if roll < 0.8 else "ONBOARDING"
            who, decision = ("senior.demo", "APPROVE") if c.status == "ACTIVE" else (None, None)
        else:
            c.status = "ACTIVE" if roll < 0.75 else "ONBOARDING"
            who, decision = (r.choice(analysts), "APPROVE") if c.status == "ACTIVE" else (None, None)
        if c.status == "ACTIVE":
            months_ago = r.randint(2, 44)
            c.onboarded_at = TODAY - relativedelta(months=months_ago)
            c.last_kyc_review = c.onboarded_at + relativedelta(months=r.randint(0, max(0, months_ago - 1)) if r.random() < 0.4 else 0)
            c.next_review_due = next_review_date(rating, c.last_kyc_review)
        if who:
            note = r.choice(["Standard CDD complete, documents verified, no adverse screening.", "EDD measures completed; senior approval granted with enhanced monitoring.",
                             "SoF supported by payslips and bank statements; risk accepted.", "ID and address verified in branch; low-risk profile.", "Approved with 12-month review cycle."])
            if rating in ("LOW", "MEDIUM") and r.random() < 0.12:
                note = r.choice(["ok", "approved", "fine"])  # deliberately thin rationales for the QA dashboard
            audit.log(db, actor=who, actor_type=audit.USER, action="CASE_DECISION", entity_type="customer", entity_id=c.id, customer_id=c.id,
                      details={"decision": decision, "note": note, "status_from": "ONBOARDING", "status_to": c.status, "risk_rating": rating})
    db.commit()


def make_reviews(db: Session, g: Gen) -> None:
    r = g.rng
    overdue = list(db.scalars(select(Customer).where(Customer.id > 11, Customer.status == "ACTIVE", Customer.next_review_due < TODAY).order_by(Customer.next_review_due)))
    for c in overdue[:16]:
        periodic.run(db, c, actor="system")
    pending = list(db.scalars(select(Review).where(Review.status == "PENDING")))
    for rv in pending[:6]:
        c = db.get(Customer, rv.customer_id)
        if c.risk_rating == "PROHIBITED":
            continue
        rv.decision, rv.decision_note, rv.decided_by = "COMPLETE_NO_CHANGE", "Documents refreshed, profile unchanged, risk rating confirmed.", r.choice(["analyst.demo", "senior.demo"])
        rv.status, rv.completed_at = "COMPLETED", NOW - timedelta(days=r.randint(1, 40))
        c.last_kyc_review = TODAY
        c.next_review_due = next_review_date(c.risk_rating or "MEDIUM", TODAY)
        audit.log(db, actor=rv.decided_by, actor_type=audit.USER, action="REVIEW_DECISION", entity_type="review", entity_id=rv.id, customer_id=c.id,
                  details={"decision": rv.decision, "note": rv.decision_note, "priority": (rv.outcome or {}).get("priority")})
    actives = list(db.scalars(select(Customer).where(Customer.id > 11, Customer.status == "ACTIVE", Customer.risk_rating.in_(["LOW", "MEDIUM"]))))
    r.shuffle(actives)
    events = [("ADDRESS_CHANGE", {"new_address": "Limassol Marina 12, Cyprus", "new_country": "Cyprus"}), ("OCCUPATION_CHANGE", {"new_occupation": "Crypto Trader", "new_industry": "Virtual asset trading"}),
              ("NEW_ADVERSE_MEDIA", {"headline": "Local businessman questioned in tax-evasion probe", "severity": "HIGH", "category": "TAX_EVASION", "source": "Regional Daily"}),
              ("NEW_SANCTIONS_MATCH", {"list_entry_id": "SAN-006", "confidence": 82}), ("ADDRESS_CHANGE", {"new_address": "Business Bay 5, Dubai", "new_country": "United Arab Emirates"}),
              ("NEW_ADVERSE_MEDIA", {"headline": "Director named in procurement fraud investigation", "severity": "MEDIUM", "category": "FRAUD", "source": "Business Courier"})]
    for c, (ev, payload) in zip(actives, events):
        try:
            event_driven.run(db, c, ev, payload, actor="system")
        except event_driven.EventError:
            db.rollback()
    db.commit()


# ---------------------------------------------------------------------------------------------- corporates
def _corp_structures(g: Gen, country: str, i: int, flavour: str):
    r = g.rng
    nodes, edges = [], []

    def person(key, verified=True, nat=None, role="Shareholder"):
        nm, n, _ = g.person(nat)
        nodes.append(dict(key=key, name=nm, node_type="PERSON", country=n, dob=g.dob(1955, 1992).isoformat(), role=role, id_verified=verified))

    if flavour == "simple":
        k = r.choice([1, 2, 3])
        shares = {1: [100], 2: [60, 40], 3: [50, 30, 20]}[k]
        for j, s in enumerate(shares):
            person(f"p{j}", verified=r.random() < 0.9)
            edges.append(dict(owner=f"p{j}", owned="ROOT", percentage=s))
    elif flavour == "holding":
        nodes.append(dict(key="h", name=f"{g.person()[0].split()[-1]} Holding {SUFFIX.get(country, 'Ltd')}", node_type="ENTITY", country=country))
        edges.append(dict(owner="h", owned="ROOT", percentage=100))
        person("p0", verified=r.random() < 0.8)
        person("p1", verified=r.random() < 0.7)
        edges += [dict(owner="p0", owned="h", percentage=65), dict(owner="p1", owned="h", percentage=35)]
    elif flavour == "offshore":
        off = r.choice(OFFSHORE)
        nodes.append(dict(key="h", name=f"{r.choice(['Atlas', 'Orion', 'Zenith', 'Meridian', 'Aurora'])} Holdings Ltd", node_type="ENTITY", country=off))
        nodes.append(dict(key="t", name=f"{r.choice(['Cedar', 'Maple', 'Birch', 'Willow'])} Family Trust", node_type="ENTITY", country=off, is_trust=True))
        nodes.append(dict(key="n", name="Nominee Directors Services Ltd", node_type="PERSON", country=off, role="Director", id_verified=False, is_nominee=True))
        person("p0", verified=False, nat=r.choice(["Turkey", "Ukraine", "Lebanon", None]))
        edges += [dict(owner="h", owned="ROOT", percentage=100), dict(owner="t", owned="h", percentage=r.choice([60, 75])), dict(owner="p0", owned="h", percentage=25 if r.random() < .5 else 20)]
    elif flavour == "incomplete":
        person("p0", verified=True)
        person("p1", verified=r.random() < 0.5)
        edges += [dict(owner="p0", owned="ROOT", percentage=r.choice([40, 45])), dict(owner="p1", owned="ROOT", percentage=r.choice([20, 25]))]
    elif flavour == "listed":
        nodes.append(dict(key="l", name=f"{g.person()[0].split()[-1]} Group plc", node_type="ENTITY", country=r.choice(["United Kingdom", "Germany", "Sweden"]), is_listed=True))
        edges.append(dict(owner="l", owned="ROOT", percentage=100))
    elif flavour == "sanctioned":
        nodes.append(dict(key="h", name="Neva Capital Partners Ltd", node_type="ENTITY", country="Cyprus"))
        nodes.append(dict(key="s", name="Dmitri Volkov", node_type="PERSON", country="Russia", dob="1985-09-09", role="Beneficial owner", id_verified=False))
        person("p0", verified=True)
        edges += [dict(owner="h", owned="ROOT", percentage=100), dict(owner="s", owned="h", percentage=r.choice([40, 55])), dict(owner="p0", owned="h", percentage=r.choice([45, 60]) if False else 45)]
    elif flavour == "pep":
        nodes.append(dict(key="s", name="Sergei Lebedev", node_type="PERSON", country="Russia", dob="1958-01-21", role="Shareholder", id_verified=True))
        person("p0", verified=True)
        edges += [dict(owner="s", owned="ROOT", percentage=35), dict(owner="p0", owned="ROOT", percentage=65)]
    return nodes, edges


def create_corporates(db: Session, g: Gen, n: int) -> list[Corporate]:
    r = g.rng
    countries = ["Poland"] * 12 + ["Germany", "Estonia", "United Kingdom", "Cyprus", "Sweden", "Netherlands", "Switzerland", "United Arab Emirates", "Malta", "Luxembourg", "Czechia", "Lithuania", "Ireland"]
    flavours = ["simple"] * 14 + ["holding"] * 9 + ["offshore"] * 6 + ["incomplete"] * 6 + ["listed"] * 3 + ["sanctioned", "pep", "pep"]
    r.shuffle(flavours)
    created = []
    for i in range(n):
        country = r.choice(countries)
        word, industry = r.choice(SECTORS)
        flavour = flavours[i % len(flavours)]
        if flavour == "sanctioned":
            industry = "Commodities trading"
        surname = g.person("Poland")[0].split()[-1].replace("ski", "ski").replace("cki", "cki")
        name = f"{surname} {word} {SUFFIX.get(country, 'Ltd')}"
        turnover = r.choice([350000, 800000, 1500000, 3200000, 6500000, 12000000, 25000000])
        op = [country] + r.sample(["Germany", "Czechia", "Poland", "Sweden", "Lithuania", "Netherlands"], r.randint(0, 2))
        if flavour in ("offshore", "sanctioned"):
            op += r.sample(["United Arab Emirates", "Turkey", "Russia", "Hong Kong"], 2)
        c = Corporate(corp_ref="TMP", legal_name=name, registration_number=f"{r.randint(100000, 999999)}{r.randint(10, 99)}", country_of_incorporation=country,
                      entity_type="LIMITED_COMPANY", industry=industry, incorporation_date=TODAY - timedelta(days=r.randint(200, 5500)),
                      registered_address=f"{r.choice(STREETS)} {r.randint(1, 99)}, {r.choice(CITY.get(country, [country]))}", operating_countries=", ".join(dict.fromkeys(op)),
                      annual_turnover=turnover, employees=max(1, turnover // r.randint(60000, 180000)), expected_activity=f"Customer receipts and supplier payments typical of a {industry.lower()} business; payroll and tax.",
                      listed=(flavour == "listed"), has_bearer_shares=(flavour == "offshore" and r.random() < 0.4), nominee_directors=(flavour == "offshore"), status="ONBOARDING")
        db.add(c)
        db.flush()
        c.corp_ref = f"CORP-{c.id:05d}"
        nodes, edges = _corp_structures(g, country, i, flavour)
        kyb.replace_structure(db, c, nodes, edges)
        audit.log(db, actor="seed-script", actor_type=audit.SYSTEM, action="CORPORATE_CREATED", entity_type="corporate", entity_id=c.id, details={"name": c.legal_name, "source": "demo-data"})
        out = kyb.run(db, c, actor="analyst.demo")
        if c.risk_rating in ("LOW", "MEDIUM") and out["ubo_status"] == "VERIFIED":
            c.status = "ACTIVE"
        elif c.risk_rating == "PROHIBITED":
            c.status = "REJECTED"
        elif c.risk_rating == "HIGH":
            c.status = "UNDER_REVIEW"
        if c.status == "ACTIVE":
            audit.log(db, actor=r.choice(["analyst.demo", "senior.demo"]), actor_type=audit.USER, action="KYB_DECISION", entity_type="corporate", entity_id=c.id,
                      details={"decision": "APPROVE", "note": "UBO verified against registry extract; standard monitoring.", "risk_rating": c.risk_rating})
        db.commit()
        created.append(c)
    return created


# ---------------------------------------------------------------------------------------------- transactions
MERCHANTS = ["Biedronka", "Żabka", "Allegro", "Amazon EU", "Zalando", "Shell", "Orange Polska", "Uber", "Netflix", "Media Markt", "IKEA", "Carrefour", "Booking.com", "LOT Airlines"]
SUPPLIERS = ["Hurtownia Centrum", "TransEuro Spedycja", "Alfa Materials GmbH", "Nordic Parts AB", "OfficeSupply Sp. z o.o.", "CloudHost EU", "Energa Biznes", "Leasing Plus"]
CLIENTS = ["Retail Clients Collective", "Euro Distribution BV", "Polmarket S.A.", "Grupa Handlowa", "Berlin Systems GmbH", "Prague Logistics", "Tech Solutions Ltd"]


def create_transactions(db: Session, g: Gen, target: int = 500) -> None:
    r = g.rng
    n = [0]

    def tx(ent, days_ago, direction, amount, channel, cp, country="Poland", hour=None):
        n[0] += 1
        ts = NOW - timedelta(days=days_ago, hours=r.randint(0, 14) if hour is None else hour)
        kw = dict(customer_id=ent.id) if isinstance(ent, Customer) else dict(corporate_id=ent.id)
        db.add(Transaction(txn_ref=f"TXN-{n[0]:06d}", ts=ts, direction=direction, amount_eur=round(amount, 2), channel=channel, counterparty=cp, counterparty_country=country, **kw))

    custs = {c.full_name: c for c in db.scalars(select(Customer))}
    corps = {c.legal_name: c for c in db.scalars(select(Corporate))}
    active_c = [c for c in custs.values() if c.status == "ACTIVE" and c.risk_rating in ("LOW", "MEDIUM", "HIGH")]
    active_k = [k for k in corps.values() if k.status == "ACTIVE"]
    # --- scripted scenarios (named so the demo can tell the story)
    mz = custs.get("Marek Zielinski")
    if mz:
        for d, amt in [(11, 9400), (9, 9100), (7, 9800), (4, 9300), (2, 9600)]:
            tx(mz, d, "IN", amt, "CASH", "Cash deposit - branch", "Poland")
    vk = custs.get("Viktor Kozlov")
    if vk:
        tx(vk, 9, "IN", 62000, "WIRE", "Neva Capital Partners Ltd", "Cyprus"); tx(vk, 8, "OUT", 58000, "WIRE", "Bosphorus Trade LLC", "Turkey")
    lh = custs.get("Lena Hoffmann")
    if lh:
        for d, amt in [(40, 25000), (28, 30000), (15, 35000), (5, 40000)]:
            tx(lh, d, "IN", amt, "CRYPTO_OFFRAMP", "NordEx OTC desk", "Estonia")
    bt = corps.get("Baltic Trade Ventures OÜ")
    if bt:
        tx(bt, 6, "IN", 240000, "WIRE", "Eurasia Commodities FZE", "United Arab Emirates", 9); tx(bt, 5, "OUT", 118000, "WIRE", "Volga Trading LLC", "Russia", 8); tx(bt, 5, "OUT", 112000, "WIRE", "Cyprus Offshore Services", "Cyprus", 14)
    if settings.seed_size == "full":  # Phase 4: planted networks & typology scenarios (own RNG - does not shift the existing data)
        from . import fiu_seed
        fiu_seed.scenario_transactions(db, tx)
    for c in r.sample(active_c, 3):  # structuring
        for d, amt in zip([15, 13, 10, 8], [9100, 9500, 8900, 9700]):
            tx(c, d, "IN", amt, "CASH", "Cash deposit - ATM", "Poland")
    for c in r.sample(active_c, 4):  # high-risk wires
        for d in (22, 14, 6):
            tx(c, d, "OUT", r.choice([6500, 8200, 12000, 15500]), "WIRE", r.choice(["Lagos Imports Ltd", "Beirut Trading Co", "Caracas Supplies SA", "Karachi Exports"]), r.choice(["Nigeria", "Lebanon", "Venezuela", "Pakistan"]))
    for k in r.sample(active_k, 4):  # pass-through
        d = r.randint(3, 20); amt = r.choice([45000, 80000, 120000])
        tx(k, d, "IN", amt, "WIRE", r.choice(CLIENTS), "Germany", 9); tx(k, d, "OUT", amt * 0.55, "WIRE", "Intermediary Holdings Ltd", "Cyprus", 13); tx(k, d, "OUT", amt * 0.4, "WIRE", "Nordic Parts AB", "Sweden", 18)
    for c in r.sample(active_c, 4):  # large vs profile
        for d in (60, 35, 12):
            tx(c, d, "IN", (c.annual_income or 40000) * r.uniform(0.9, 1.4), "WIRE", "Unspecified third party", r.choice(["United Arab Emirates", "Cyprus", "Turkey"]))
    for c in r.sample(active_c, 4):
        tx(c, r.randint(2, 30), "IN", r.choice([12000, 15000, 18500]), "CASH", "Cash deposit - branch")
    for c in r.sample(active_c, 3):  # round-sum cluster
        for d in (24, 19, 14, 9, 4):
            tx(c, d, r.choice(["IN", "OUT"]), 5000 * r.randint(1, 3), "WIRE", "Private individual", "Poland")
    # --- baseline behaviour
    for c in r.sample(active_c, min(len(active_c), 60)):
        sal = (c.annual_income or 36000) / 12 * 0.78
        for m in (0, 1):
            tx(c, 4 + 30 * m + r.randint(0, 2), "IN", sal, "SEPA", r.choice(EMPLOYERS), "Poland")
        tx(c, r.randint(3, 60), "OUT", sal * 0.3, "SEPA", "Landlord / mortgage", "Poland")
        tx(c, r.randint(1, 40), "OUT", r.uniform(20, 400), "CARD", r.choice(MERCHANTS), "Poland")
    for k in r.sample(active_k, min(len(active_k), 18)):
        base = (k.annual_turnover or 800000) / 12
        for m in (0, 1):
            tx(k, 5 + 30 * m, "IN", base * r.uniform(0.5, 1.1), "SEPA", r.choice(CLIENTS), r.choice(["Poland", "Germany", "Czechia"]))
            tx(k, 9 + 30 * m, "OUT", base * r.uniform(0.3, 0.8), "SEPA", r.choice(SUPPLIERS), r.choice(["Poland", "Germany", "Sweden"]))
    db.flush()
    # --- pad with ordinary card / transfer activity to exactly `target`
    pool = [*active_c, *active_k]
    while n[0] < target:
        e = r.choice(pool)
        if isinstance(e, Customer):
            tx(e, r.randint(0, 80), "OUT", r.uniform(15, 450), "CARD", r.choice(MERCHANTS))
        else:
            tx(e, r.randint(0, 80), r.choice(["IN", "OUT"]), r.uniform(1500, 40000), "SEPA", r.choice(CLIENTS + SUPPLIERS))
    if n[0] > target:  # scenarios + baseline overshot: trim the cheapest ordinary rows
        extra = n[0] - target
        db.flush()
        rows = list(db.scalars(select(Transaction).where(Transaction.channel == "CARD").order_by(Transaction.id.desc()).limit(extra)))
        for row in rows:
            db.delete(row)
    db.commit()
    monitor(db)
    db.commit()


# ---------------------------------------------------------------------------------------------- cases, SARs, QA, polish
def work_the_queue(db: Session, g: Gen) -> None:
    """Spread alerts across workflow states and back-date them so trend charts have shape."""
    r = g.rng
    alerts = list(db.scalars(select(Alert).order_by(Alert.id)))
    for a in alerts:
        if a.status in ("ESCALATED_MLRO", "SAR_DRAFTED"):
            continue
        roll = r.random()
        if roll < 0.28:
            a.status, a.assigned_to = "CLOSED", r.choice(["analyst.demo", "senior.demo"])
            a.resolution = r.choice(["Reviewed transactions against profile; activity explained by documented business purpose.", "False positive - different person (DOB and nationality mismatch confirmed with ID document).",
                                     "Customer provided SoF evidence; no further action, continue monitoring.", "Sanctions match discounted after review of list entry and passport data."])
            a.closed_at = NOW - timedelta(days=r.randint(0, 30))
        elif roll < 0.5:
            a.status, a.assigned_to = "IN_REVIEW", r.choice(["analyst.demo", "senior.demo"])
        elif roll < 0.7:
            a.assigned_to = r.choice(["analyst.demo", "senior.demo"])
    open_high = [a for a in alerts if a.status in ("OPEN", "IN_REVIEW") and a.severity in ("HIGH", "CRITICAL") and a.entity_type == "customer"]
    seen_src: set[str] = set()
    picked = []
    for a in open_high:
        if a.source not in seen_src and len(picked) < 4:
            seen_src.add(a.source)
            picked.append(a)
    for a in picked:
        a.status, a.escalated_at, a.assigned_to = "ESCALATED_MLRO", NOW - timedelta(days=r.randint(0, 5)), "senior.demo"
        a.resolution = "Escalated: indicators not explained by customer profile; MLRO decision needed on SAR."
        audit.log(db, actor="senior.demo", actor_type=audit.USER, action="ALERT_ACTION", entity_type="alert", entity_id=a.id, customer_id=a.customer_id,
                  details=dict(action="ESCALATE", note=a.resolution, status_to="ESCALATED_MLRO", priority=a.severity))
    # back-date: open work is mostly recent, closed work is older - gives the ageing and case-volume charts a believable shape
    for a in alerts:
        if a.status in ("OPEN", "IN_REVIEW"):
            age = int(r.triangular(0, 38, 4))
        elif a.status in ("ESCALATED_MLRO", "SAR_DRAFTED"):
            age = r.randint(1, 9)
        else:
            age = r.randint(12, 170)
        a.created_at = NOW - timedelta(days=age, hours=r.randint(0, 20))
        if a.closed_at:
            a.closed_at = min(NOW, a.created_at + timedelta(days=r.randint(1, 9)))
        if a.escalated_at:
            a.escalated_at = min(NOW, a.created_at + timedelta(days=r.randint(0, 2)))
    reviews = list(db.scalars(select(Review).order_by(Review.id)))
    for idx, rv in enumerate(reviews):
        rv.created_at = NOW - timedelta(days=int((len(reviews) - idx) / max(1, len(reviews)) * 120) + r.randint(0, 3))
        if rv.completed_at:
            rv.completed_at = min(NOW, rv.created_at + timedelta(days=r.randint(1, 12)))
    db.commit()


def make_sars(db: Session, g: Gen) -> None:
    r = g.rng
    existing = list(db.scalars(select(Sar)))
    subjects = [(c.id, "customer") for c in db.scalars(select(Customer).where(Customer.risk_rating.in_(["HIGH", "PROHIBITED"])).order_by(Customer.risk_score.desc()))]
    subjects = [s for s in subjects if s[0] not in {x.subject_id for x in existing if x.subject_type == "customer"}][:7]
    kcorps = [(k.id, "corporate") for k in db.scalars(select(Corporate).where(Corporate.risk_rating.in_(["HIGH", "PROHIBITED"])).order_by(Corporate.risk_score.desc()))][:3]
    plan = ["FILED", "FILED", "FILED", "FILED", "APPROVED", "PENDING_MLRO", "REJECTED", "DRAFT", "FILED", "DRAFT"]
    for (sid, stype), status in zip(subjects[:6] + kcorps[:4], plan):
        s = sarsvc.generate(db, stype, sid, actor=r.choice(["analyst.demo", "senior.demo"]))
        age = r.randint(8, 160)
        s.created_at = NOW - timedelta(days=age)
        if status != "DRAFT":
            s.submitted_at = s.created_at + timedelta(days=r.randint(1, 4))
        if status in ("APPROVED", "FILED", "REJECTED"):
            s.approved_by, s.decided_at = "mlro.demo", s.submitted_at + timedelta(days=r.randint(1, 3))
            s.mlro_note = "Grounds for suspicion documented; approved for filing." if status != "REJECTED" else "Insufficient grounds - request further customer due diligence and re-submit if still unexplained."
        s.status = status
        if status == "FILED":
            s.filing_reference = f"FIU-SIM-{s.decided_at:%Y%m%d}-{s.id:04d}"
        audit.log(db, actor="mlro.demo" if status in ("APPROVED", "FILED", "REJECTED") else s.prepared_by, actor_type=audit.USER, action="SAR_MLRO_DECISION" if s.approved_by else "SAR_SUBMITTED",
                  entity_type="sar", entity_id=s.id, customer_id=s.customer_id, details=dict(decision=status, reference=s.reference, priority="CRITICAL", note=s.mlro_note or ""))
    db.commit()


def finish_qa_and_reports(db: Session, g: Gen) -> None:
    r = g.rng
    qa.sample(db, days=365, low_risk_rate=0.35, actor="manager.demo")
    db.commit()
    from .models import QaReview

    pending = list(db.scalars(select(QaReview).where(QaReview.status == "PENDING").order_by(QaReview.id)))
    crit = list(qa.CHECKLISTS["default"])
    done = 0
    for q in pending:
        if done >= 14:
            break
        reviewer = r.choice(["senior.demo", "manager.demo"])
        if reviewer == q.decision_maker:
            continue
        answers = {k: "PASS" for k in crit}
        findings = None
        if any(f for f in q.precheck) or r.random() < 0.18:
            answers[r.choice(crit)] = "FAIL"
            findings = "Rationale too thin / evidence not referenced in the decision note; coach analyst and re-document."
        try:
            qa.complete(q, reviewer, answers, findings)
            q.completed_at = NOW - timedelta(days=r.randint(0, 40))
            done += 1
        except (ValueError, PermissionError):
            continue
    db.commit()
    today = date.today()
    for rtype, start, end, status in [("SAR_STATISTICS", today - timedelta(days=180), today - timedelta(days=91), "SUBMITTED"), ("CUSTOMER_RISK_MI", today - timedelta(days=90), today, "DRAFT"),
                                      ("KYB_UBO", today - timedelta(days=90), today, "APPROVED")]:
        rep = reporting.generate(db, rtype, start, end, actor="manager.demo")
        if status in ("APPROVED", "SUBMITTED"):
            rep.status, rep.approved_by, rep.approved_at = "APPROVED", "mlro.demo", NOW - timedelta(days=3)
        if status == "SUBMITTED":
            rep.status, rep.submitted_at = "SUBMITTED", NOW - timedelta(days=2)
            rep.submission_reference = f"REG-SIM-{rep.submitted_at:%Y%m%d}-{rep.id:04d}"
    db.commit()


def spread_audit_timestamps(db: Session) -> None:
    """Make the audit trail span ~170 days instead of 'everything happened in the last minute' (monotonic in id)."""
    ids = list(db.scalars(select(AuditLog.id).order_by(AuditLog.id)))
    n = len(ids)
    if not n:
        return
    span = timedelta(days=170)
    keep_recent = max(1, int(n * 0.03))  # the last 3% (seed-time QA/report work) stays "now"
    for pos, aid in enumerate(ids[:-keep_recent]):
        db.execute(update(AuditLog).where(AuditLog.id == aid).values(ts=NOW - span + span * (pos / max(1, n - keep_recent))))
    db.commit()


def extend(db: Session) -> dict:
    """Grow the (already seeded) 11 customers / 5 corporates to 100 / 50 and add transactions, cases, SARs and QA."""
    prior = settings.llm_enabled
    settings.llm_enabled = False
    try:
        g = Gen()
        have_c = db.scalar(select(func.count(Customer.id))) or 0
        for name in db.scalars(select(Customer.full_name)):
            g.used.add(name)
        for name in db.scalars(select(Corporate.legal_name)):
            g.used.add(name)
        specs = build_customers(g, 100 - have_c)
        new_customers = create_customers(db, specs, have_c + 1)
        decide_statuses(db, g, new_customers)
        have_k = db.scalar(select(func.count(Corporate.id))) or 0
        create_corporates(db, g, 50 - have_k)
        from . import fiu_seed
        fiu_seed.seed_identifiers(db)
        fiu_seed.seed_chain_extras(db)
        db.flush()
        create_transactions(db, g, 500)
        make_reviews(db, g)
        work_the_queue(db, g)
        make_sars(db, g)
        finish_qa_and_reports(db, g)
        fiu_seed.seed_investigations(db) if settings.seed_size == "full" else None
        spread_audit_timestamps(db)
        return dict(customers=db.scalar(select(func.count(Customer.id))), corporates=db.scalar(select(func.count(Corporate.id))),
                    transactions=db.scalar(select(func.count(Transaction.id))), alerts=db.scalar(select(func.count(Alert.id))))
    finally:
        settings.llm_enabled = prior


def seed_everything(db: Session) -> dict:
    from .seed import seed
    from .seed_ext import seed_ext

    seed_users(db)
    seed(db)
    seed_ext(db)
    return extend(db) if settings.seed_size == "full" else {}


def reset_and_seed(db: Session) -> dict:
    """Admin 'reset demo' - wipe every table (children first) and rebuild the dataset."""
    from .db import Base

    db.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(delete(table))
    db.commit()
    return seed_everything(db)
