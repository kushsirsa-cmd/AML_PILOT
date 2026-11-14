"""Illustrative risk reference tables. NOT an official FATF/EU list - tune to your own risk-based approach."""

PROHIBITED_COUNTRIES = {"north korea", "iran", "syria"}

HIGH_RISK_COUNTRIES = {
    "russia", "belarus", "myanmar", "venezuela", "yemen", "afghanistan", "haiti", "south sudan",
    "libya", "somalia", "sudan", "mali", "nigeria", "lebanon", "democratic republic of the congo",
}

MEDIUM_RISK_COUNTRIES = {
    "united arab emirates", "turkey", "pakistan", "panama", "cyprus", "malta", "bulgaria", "romania",
    "south africa", "philippines", "vietnam", "kenya", "ukraine", "serbia", "albania", "cayman islands",
    "british virgin islands", "hong kong", "china", "india", "brazil", "colombia", "mexico", "kazakhstan",
}

COUNTRY_ALIASES = {
    "dprk": "north korea",
    "democratic people's republic of korea": "north korea",
    "islamic republic of iran": "iran",
    "russian federation": "russia",
    "burma": "myanmar",
    "uae": "united arab emirates",
    "uk": "united kingdom",
    "great britain": "united kingdom",
    "usa": "united states",
    "us": "united states",
    "republic of turkey": "turkey",
    "türkiye": "turkey",
    "turkiye": "turkey",
    "drc": "democratic republic of the congo",
    "polska": "poland",
}

COUNTRY_SCORES = {"PROHIBITED": 100, "HIGH": 28, "MEDIUM": 12, "LOW": 0, "UNKNOWN": 8}

# (keywords, label, level, score) - first match wins, ordered by severity
INDUSTRY_RULES = [
    (("crypto", "virtual asset", "bitcoin", "digital asset"), "Virtual assets", "HIGH", 24),
    (("casino", "gambling", "betting", "gaming operator"), "Gambling", "HIGH", 24),
    (("money service", "remittance", "money transfer", "exchange bureau", "currency exchange", "hawala"), "Money service business", "HIGH", 25),
    ((" arms ", "weapon", "defence", "defense", "military", "ammunition"), "Arms & defence", "HIGH", 25),
    (("precious metal", "gold dealer", "gold trad", "bullion", "diamond", "jewel"), "Precious metals & stones", "HIGH", 22),
    (("shell company", "offshore", "nominee", "trust and company"), "Corporate vehicles / offshore", "HIGH", 22),
    (("art dealer", "antiques", "auction house", "art gallery"), "Art & antiques", "MEDIUM", 15),
    (("oil and gas", " oil ", " gas ", "mining", "extractive"), "Extractive industries", "MEDIUM", 15),
    (("real estate", "property developer", "construction"), "Real estate & construction", "MEDIUM", 14),
    (("import", "export", "trading", "trade ", "logistics", "shipping"), "Import/export & trading", "MEDIUM", 12),
    (("restaurant", "nightclub", "hospitality", "retail", "car dealer", "used car", "cash-intensive"), "Cash-intensive business", "MEDIUM", 12),
    (("consult", "advisory", "freelance"), "Consultancy / services", "MEDIUM", 8),
]
DEFAULT_INDUSTRY = ("General / low-risk sector", "LOW", 0)

PRODUCT_SCORES = {
    "CURRENT_ACCOUNT": 4, "SAVINGS": 2, "CREDIT_CARD": 5, "MORTGAGE": 4, "INVESTMENT": 10,
    "INTERNATIONAL_WIRES": 15, "PRIVATE_BANKING": 20, "TRADE_FINANCE": 22, "CORRESPONDENT": 25,
    "CRYPTO_CUSTODY": 25,
}
CHANNEL_SCORES = {"FACE_TO_FACE": 0, "ONLINE": 6, "INTERMEDIARY": 10, "REMOTE_NO_ID_CHECK": 15}

REVIEW_CYCLE_MONTHS = {"LOW": 36, "MEDIUM": 24, "HIGH": 12}

REQUIRED_DOCS = {
    "LOW": ["ID_DOCUMENT", "PROOF_OF_ADDRESS"],
    "MEDIUM": ["ID_DOCUMENT", "PROOF_OF_ADDRESS", "SOF_EVIDENCE"],
    "HIGH": ["ID_DOCUMENT", "PROOF_OF_ADDRESS", "SOF_EVIDENCE", "SOW_EVIDENCE"],
    "PROHIBITED": ["ID_DOCUMENT", "PROOF_OF_ADDRESS"],
}

RATING_ORDER = ["LOW", "MEDIUM", "HIGH", "PROHIBITED"]


def norm_country(value: str | None) -> str:
    v = (value or "").strip().lower()
    return COUNTRY_ALIASES.get(v, v)


def country_risk(value: str | None) -> dict:
    c = norm_country(value)
    if not c:
        return {"level": "UNKNOWN", "score": COUNTRY_SCORES["UNKNOWN"], "reason": "Country not provided."}
    if c in PROHIBITED_COUNTRIES:
        return {"level": "PROHIBITED", "score": COUNTRY_SCORES["PROHIBITED"], "reason": f"{value} is on the comprehensive-sanctions / prohibited jurisdiction list."}
    if c in HIGH_RISK_COUNTRIES:
        return {"level": "HIGH", "score": COUNTRY_SCORES["HIGH"], "reason": f"{value} is classed as a high-risk jurisdiction (illustrative FATF / EU / corruption-index based list)."}
    if c in MEDIUM_RISK_COUNTRIES:
        return {"level": "MEDIUM", "score": COUNTRY_SCORES["MEDIUM"], "reason": f"{value} is classed as a medium-risk jurisdiction."}
    return {"level": "LOW", "score": COUNTRY_SCORES["LOW"], "reason": f"{value} is not on the high/medium-risk reference lists."}


def industry_risk(value: str | None) -> dict:
    v = f" {(value or '').strip().lower()} "
    for keywords, label, level, score in INDUSTRY_RULES:
        if any(k in v for k in keywords):
            return {"level": level, "score": score, "category": label, "reason": f"Industry '{value}' maps to '{label}'."}
    label, level, score = DEFAULT_INDUSTRY
    return {"level": level, "score": score, "category": label, "reason": f"Industry '{value}' has no elevated-risk indicators."}


def level_from_score(score: float, high: float = 20, medium: float = 8) -> str:
    return "HIGH" if score >= high else "MEDIUM" if score >= medium else "LOW"
