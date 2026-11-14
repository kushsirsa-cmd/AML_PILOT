"""KYC Agent: completeness, consistency and red-flag review of the intake profile."""
from datetime import date

from ..models import Customer
from .base import age_on, customer_facts, narrate

REQUIRED = {
    "full_name": "Full name",
    "date_of_birth": "Date of birth",
    "nationality": "Nationality",
    "country_of_residence": "Country of residence",
    "address": "Residential address",
    "occupation": "Occupation",
    "industry": "Industry",
    "source_of_funds": "Source of funds",
    "source_of_wealth": "Source of wealth",
    "expected_activity": "Expected account activity",
    "annual_income": "Annual income",
}
VAGUE_OCCUPATIONS = {"self-employed", "self employed", "businessman", "business", "consultant", "freelancer", "n/a", "na", "other", "none", "unknown"}
NON_EARNING = ("student", "unemployed", "retired", "homemaker", "housewife", "not working")


def run(db, c: Customer, ctx: dict) -> dict:
    missing: list[str] = []
    for attr, label in REQUIRED.items():
        v = getattr(c, attr, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(label)

    notes: list[str] = []
    if c.date_of_birth:
        if c.date_of_birth > date.today():
            notes.append("Date of birth is in the future - data quality error.")
        else:
            age = age_on(c.date_of_birth)
            if age < 18:
                notes.append(f"Customer is {age} years old - below the minimum age for standard onboarding.")
            elif age > 90:
                notes.append(f"Customer is {age} years old - verify identity details and capacity.")
    occ = (c.occupation or "").strip().lower()
    if occ in VAGUE_OCCUPATIONS:
        notes.append(f"Occupation '{c.occupation}' is vague - obtain employer / business name and role.")
    if any(k in occ for k in NON_EARNING) and (c.annual_income or 0) > 30000:
        notes.append(f"Occupation '{c.occupation}' is inconsistent with declared annual income of EUR {c.annual_income:,.0f}.")
    if c.nationality and c.country_of_residence and c.nationality.strip().lower() != c.country_of_residence.strip().lower():
        notes.append(f"Nationality ({c.nationality}) differs from country of residence ({c.country_of_residence}) - confirm residency basis and ties to the country.")
    if c.source_of_funds and len(c.source_of_funds.strip()) < 25:
        notes.append("Source of funds statement is very brief and non-specific.")
    if c.source_of_wealth and len(c.source_of_wealth.strip()) < 25:
        notes.append("Source of wealth statement is very brief and non-specific.")
    if c.pep_declared:
        notes.append("Customer self-declared as a Politically Exposed Person.")
    if c.channel == "REMOTE_NO_ID_CHECK":
        notes.append("Customer onboarded remotely without documentary identity verification.")
    if any(ch.isdigit() for ch in c.full_name or ""):
        notes.append("Name contains digits - possible data-entry error or alias.")

    total = len(REQUIRED)
    completeness = round(100 * (total - len(missing)) / total)

    fallback = (
        f"{c.full_name} ({c.nationality} national, resident in {c.country_of_residence}) works as {c.occupation} "
        f"in the {c.industry} sector with a declared annual income of "
        f"{'EUR {:,.0f}'.format(c.annual_income) if c.annual_income is not None else 'an unspecified amount'}. "
        f"The KYC profile is {completeness}% complete"
        + (f"; missing: {', '.join(missing)}. " if missing else ". ")
        + (f"{len(notes)} KYC risk note(s) were raised." if notes else "No KYC risk notes were raised.")
    )
    summary, engine = narrate(
        "Write a KYC summary for the analyst covering who the customer is, how complete the profile is, and the main concerns.",
        {"customer": customer_facts(c), "completeness_pct": completeness, "missing_information": missing, "risk_notes": notes},
        fallback,
    )
    return {
        "kyc_summary": summary,
        "completeness_pct": completeness,
        "missing_information": missing,
        "kyc_risk_notes": notes,
        "engine": engine,
    }
