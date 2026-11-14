"""FATF Recommendation 16 / EU Transfer of Funds Regulation (Travel Rule) checks for crypto-asset transfers."""
import json
from pathlib import Path

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..data.risk_tables import country_risk
from ..models import AddressLabel, Customer, TravelRuleTransfer, Wallet
from ..screening_service import normalise_name, screen
from .alerts import raise_alert
from .chain import CATEGORY_WEIGHT

THRESHOLD_EUR = 1000.0  # information must accompany every transfer; extra duties (identifier, self-hosted proof) apply from this amount
REGISTRY = json.loads((Path(__file__).parent.parent / "data" / "vasp_registry.json").read_text(encoding="utf-8"))


def find_vasp(name: str | None) -> dict | None:
    n = normalise_name(name or "")
    return next((v for v in REGISTRY if normalise_name(v["name"]) == n), None) if n else None


def _prefill(db: Session, p: dict) -> dict:
    """For our own customer's side of the transfer, fill known data (name, address, DOB, wallet address)."""
    cid = p.get("customer_id")
    if not cid:
        return p
    c = db.get(Customer, cid)
    w = db.get(Wallet, p["wallet_id"]) if p.get("wallet_id") else None
    side = "originator" if p["direction"] == "OUT" else "beneficiary"
    party = dict(p.get(side) or {})
    if c:
        party.setdefault("name", c.full_name)
        party.setdefault("address", c.address)
        if side == "originator":
            party.setdefault("dob", c.date_of_birth.isoformat())
            party.setdefault("country", c.country_of_residence)
    if w:
        party.setdefault("account", w.address)
    p[side] = {k: v for k, v in party.items() if v}
    return p


def evaluate(db: Session, p: dict) -> dict:
    p = _prefill(db, dict(p))
    orig, ben = p.get("originator") or {}, p.get("beneficiary") or {}
    amount = float(p["amount_eur"])
    full = amount >= THRESHOLD_EUR
    checks: list[dict] = []

    def chk(name: str, result: str, severity: str, detail: str):
        checks.append(dict(check=name, result=result, severity=severity, detail=detail))

    chk("THRESHOLD", "PASS", "INFO", f"EUR {amount:,.2f} {'>=' if full else '<'} EUR {THRESHOLD_EUR:,.0f}: "
        + ("full originator / beneficiary information and self-hosted-wallet controls apply." if full else "basic name + account information required."))
    for label, party, side in (("ORIGINATOR", orig, "originator"), ("BENEFICIARY", ben, "beneficiary")):
        chk(f"{label}_NAME", "PASS" if party.get("name") else "FAIL", "MANDATORY", f"{side.title()} name {'present' if party.get('name') else 'missing'}.")
        chk(f"{label}_ACCOUNT", "PASS" if party.get("account") else "FAIL", "MANDATORY", f"{side.title()} wallet address / account {'present' if party.get('account') else 'missing'}.")
    if full:
        ident = orig.get("address") or orig.get("national_id") or orig.get("dob")
        chk("ORIGINATOR_IDENTIFIER", "PASS" if ident else "FAIL", "MANDATORY",
            "Originator geographic address, national ID or date of birth " + ("present." if ident else "missing (required from the threshold)."))

    # counterparty VASP
    vasp = None
    if p.get("self_hosted"):
        chk("COUNTERPARTY_VASP", "SKIP", "INFO", "Transfer to / from a self-hosted (unhosted) wallet - no counterparty VASP.")
        if full:
            chk("SELF_HOSTED_OWNERSHIP_PROOF", "PASS" if p.get("ownership_proof") else "FAIL", "MANDATORY",
                "Ownership / control of the self-hosted wallet " + ("has been verified." if p.get("ownership_proof") else "has not been verified (e.g. signed message or micro-transfer)."))
    else:
        vasp = find_vasp(p.get("counterparty_vasp"))
        if not p.get("counterparty_vasp"):
            chk("COUNTERPARTY_VASP", "FAIL", "MANDATORY", "Counterparty VASP not identified.")
        elif not vasp:
            chk("COUNTERPARTY_VASP", "FAIL", "MANDATORY", f"'{p['counterparty_vasp']}' is not in the VASP registry - counterparty due diligence required.")
        elif vasp["licence_status"] != "LICENSED":
            chk("COUNTERPARTY_VASP", "FAIL", "CRITICAL", f"{vasp['name']} is {vasp['licence_status']} ({vasp['notes']}).")
        else:
            chk("COUNTERPARTY_VASP", "PASS", "MANDATORY", f"{vasp['name']} ({vasp['country']}) is licensed.")
            if vasp["protocol"] == "none":
                chk("TRAVEL_RULE_PROTOCOL", "WARN", "ADVISORY", f"{vasp['name']} supports no Travel Rule messaging protocol - exchange data out-of-band and document it.")
            else:
                chk("TRAVEL_RULE_PROTOCOL", "PASS", "ADVISORY", f"Counterparty reachable via {vasp['protocol']}.")

    # sanctions screening of named parties
    for label, party in (("ORIGINATOR", orig), ("BENEFICIARY", ben)):
        if not party.get("name"):
            continue
        dob = None
        try:
            from datetime import date
            dob = date.fromisoformat(party["dob"]) if party.get("dob") else None
        except ValueError:
            pass
        hits = [h for h in screen(party["name"], dob, party.get("country"))["SANCTIONS"] if h["confidence"] >= 75]
        if hits:
            top = hits[0]
            sev = "CRITICAL" if top["confidence"] >= 90 else "MANDATORY"
            chk(f"{label}_SANCTIONS", "FAIL", sev, f"{party['name']} matches sanctions entry '{top['matched_name']}' at {top['confidence']:.0f}% ({top['record'].get('list')}).")
        else:
            chk(f"{label}_SANCTIONS", "PASS", "MANDATORY", f"No sanctions match for {party['name']}.")

    # on-chain attribution of the counterparty address
    cp_account = (orig if p["direction"] == "IN" else ben).get("account")
    if cp_account:
        lab = db.get(AddressLabel, cp_account)
        w = CATEGORY_WEIGHT.get(lab.category, 0) if lab else 0
        if lab and w >= 0.8:
            chk("COUNTERPARTY_ADDRESS_ATTRIBUTION", "FAIL", "CRITICAL", f"Counterparty address is attributed to {lab.entity_name} ({lab.category}).")
        elif lab and w >= 0.3:
            chk("COUNTERPARTY_ADDRESS_ATTRIBUTION", "WARN", "ADVISORY", f"Counterparty address is attributed to {lab.entity_name} ({lab.category}).")
        else:
            chk("COUNTERPARTY_ADDRESS_ATTRIBUTION", "PASS", "ADVISORY", "No risky attribution for the counterparty address." if not lab else f"Attributed to {lab.entity_name} ({lab.category}).")

    # jurisdiction
    country = (vasp or {}).get("country") or (orig if p["direction"] == "IN" else ben).get("country")
    if country:
        r = country_risk(country)
        if r["level"] == "PROHIBITED":
            chk("COUNTERPARTY_JURISDICTION", "FAIL", "CRITICAL", r["reason"])
        elif r["level"] == "HIGH":
            chk("COUNTERPARTY_JURISDICTION", "WARN", "ADVISORY", r["reason"])
        else:
            chk("COUNTERPARTY_JURISDICTION", "PASS", "ADVISORY", f"{country}: {r['level']} risk.")

    # is the customer-side party really the customer? (third-party transfers)
    if p.get("customer_id"):
        c = db.get(Customer, p["customer_id"])
        own = (ben if p["direction"] == "IN" else orig).get("name")
        if c and own:
            score = fuzz.token_sort_ratio(normalise_name(c.full_name), normalise_name(own))
            if score < 80:
                chk("CUSTOMER_NAME_MATCH", "WARN", "ADVISORY", f"Name on transfer '{own}' differs from customer '{c.full_name}' ({score:.0f}% similar) - possible third-party transfer.")
            else:
                chk("CUSTOMER_NAME_MATCH", "PASS", "ADVISORY", "Transfer party matches the customer name.")

    crit = [c for c in checks if c["result"] == "FAIL" and c["severity"] == "CRITICAL"]
    mand = [c for c in checks if c["result"] == "FAIL" and c["severity"] == "MANDATORY"]
    warn = [c for c in checks if c["result"] == "WARN"]
    status = "REJECT" if crit else "HOLD_REQUEST_INFO" if mand else "ACCEPT_WITH_REVIEW" if warn else "ACCEPT"
    reasons = [c["detail"] for c in crit + mand + warn]
    return dict(payload=p, checks=checks, status=status, reasons=reasons, applicable_full_rule=full)


def check_and_store(db: Session, p: dict, actor: str = "system") -> TravelRuleTransfer:
    r = evaluate(db, p)
    p = r["payload"]
    t = TravelRuleTransfer(
        customer_id=p.get("customer_id"), corporate_id=p.get("corporate_id"), wallet_id=p.get("wallet_id"), direction=p["direction"],
        tx_hash=p.get("tx_hash"), asset=p.get("asset", "USDT"), amount_eur=float(p["amount_eur"]), originator=p.get("originator") or {},
        beneficiary=p.get("beneficiary") or {}, counterparty_vasp=p.get("counterparty_vasp"), self_hosted=bool(p.get("self_hosted")),
        ownership_proof=bool(p.get("ownership_proof")), checks=r["checks"], status=r["status"], reasons=r["reasons"],
    )
    db.add(t)
    db.flush()
    audit.log(db, actor="Travel Rule Engine", actor_type=audit.AI, action="TRAVEL_RULE_CHECK", entity_type="transfer", entity_id=t.id,
              customer_id=t.customer_id, details=dict(requested_by=actor, status=t.status, amount_eur=t.amount_eur, reasons=t.reasons[:4]))
    if t.status == "REJECT":
        raise_alert(db, source="TRAVEL_RULE", entity_type="transfer", entity_id=t.id, customer_id=t.customer_id, severity="CRITICAL"
                    if any("sanction" in x.lower() or "SANCTIONED" in x for x in t.reasons) else "HIGH",
                    title=f"Travel Rule: {t.direction} transfer of EUR {t.amount_eur:,.0f} rejected", description=" | ".join(t.reasons[:3]),
                    details=dict(tx_hash=t.tx_hash, vasp=t.counterparty_vasp))
    return t


def transfer_dict(t: TravelRuleTransfer) -> dict:
    return dict(id=t.id, customer_id=t.customer_id, corporate_id=t.corporate_id, wallet_id=t.wallet_id, direction=t.direction, tx_hash=t.tx_hash,
                asset=t.asset, amount_eur=t.amount_eur, originator=t.originator, beneficiary=t.beneficiary, counterparty_vasp=t.counterparty_vasp,
                self_hosted=t.self_hosted, ownership_proof=t.ownership_proof, checks=t.checks, status=t.status, reasons=t.reasons,
                created_at=t.created_at.isoformat())
