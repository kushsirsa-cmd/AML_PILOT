from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user
from ..models import TravelRuleTransfer
from ..modules import travel_rule as tr

router = APIRouter(prefix="/api/travel-rule", tags=["travel-rule"])


class Party(BaseModel):
    name: str | None = None
    account: str | None = None
    address: str | None = None
    national_id: str | None = None
    dob: str | None = None
    country: str | None = None


class TransferIn(BaseModel):
    direction: str = Field(pattern="^(IN|OUT)$")
    amount_eur: float = Field(gt=0)
    asset: str = "USDT"
    tx_hash: str | None = None
    originator: Party = Party()
    beneficiary: Party = Party()
    counterparty_vasp: str | None = None
    self_hosted: bool = False
    ownership_proof: bool = False
    customer_id: int | None = None
    corporate_id: int | None = None
    wallet_id: int | None = None

    def as_payload(self) -> dict:
        d = self.model_dump()
        d["originator"] = {k: v for k, v in d["originator"].items() if v}
        d["beneficiary"] = {k: v for k, v in d["beneficiary"].items() if v}
        return d


class ResolveIn(BaseModel):
    action: str = Field(pattern="^(RELEASE|RETURN_FUNDS|REPORT_TO_MLRO)$")
    note: str = Field(min_length=3)
    originator: Party | None = None
    beneficiary: Party | None = None
    ownership_proof: bool | None = None
    counterparty_vasp: str | None = None


@router.get("/vasps")
def vasps():
    return {"threshold_eur": tr.THRESHOLD_EUR, "vasps": tr.REGISTRY}


@router.post("/evaluate")
def evaluate(body: TransferIn, db: Session = Depends(get_db)):
    """Dry run: returns the checks and status without storing anything."""
    r = tr.evaluate(db, body.as_payload())
    return dict(status=r["status"], checks=r["checks"], reasons=r["reasons"])


@router.post("/check", status_code=201)
def check(body: TransferIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    t = tr.check_and_store(db, body.as_payload(), actor=user)
    db.commit()
    return tr.transfer_dict(t)


@router.get("/transfers")
def transfers(status: str | None = None, customer_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(TravelRuleTransfer).order_by(TravelRuleTransfer.id.desc())
    if status:
        stmt = stmt.where(TravelRuleTransfer.status == status)
    if customer_id:
        stmt = stmt.where(TravelRuleTransfer.customer_id == customer_id)
    return [tr.transfer_dict(t) for t in db.scalars(stmt)]


@router.post("/transfers/{transfer_id}/resolve")
def resolve(transfer_id: int, body: ResolveIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    t = db.get(TravelRuleTransfer, transfer_id)
    if not t:
        raise HTTPException(404, "Transfer not found")
    if t.status not in ("HOLD_REQUEST_INFO", "REJECT", "ACCEPT_WITH_REVIEW"):
        raise HTTPException(409, f"Transfer already {t.status}")
    if body.action == "RELEASE":
        payload = dict(direction=t.direction, amount_eur=t.amount_eur, asset=t.asset, tx_hash=t.tx_hash, originator=dict(t.originator), beneficiary=dict(t.beneficiary),
                       counterparty_vasp=body.counterparty_vasp or t.counterparty_vasp, self_hosted=t.self_hosted,
                       ownership_proof=t.ownership_proof if body.ownership_proof is None else body.ownership_proof, customer_id=t.customer_id,
                       corporate_id=t.corporate_id, wallet_id=t.wallet_id)
        if body.originator:
            payload["originator"].update({k: v for k, v in body.originator.model_dump().items() if v})
        if body.beneficiary:
            payload["beneficiary"].update({k: v for k, v in body.beneficiary.model_dump().items() if v})
        r = tr.evaluate(db, payload)
        if r["status"] in ("REJECT", "HOLD_REQUEST_INFO"):
            raise HTTPException(409, "Cannot release - checks still failing: " + " | ".join(r["reasons"][:3]))
        t.originator, t.beneficiary, t.counterparty_vasp = r["payload"]["originator"], r["payload"]["beneficiary"], r["payload"].get("counterparty_vasp")
        t.ownership_proof, t.checks, t.reasons, t.status = bool(payload["ownership_proof"]), r["checks"], r["reasons"], "ACCEPT" if r["status"] == "ACCEPT" else "ACCEPT_WITH_REVIEW"
        new_status = "RELEASED"
    else:
        new_status = "RETURNED" if body.action == "RETURN_FUNDS" else "ESCALATED_MLRO"
        t.status = new_status
    audit.log(db, actor=user, actor_type=audit.USER, action="TRAVEL_RULE_RESOLUTION", entity_type="transfer", entity_id=t.id, customer_id=t.customer_id,
              details={"action": body.action, "note": body.note, "status": t.status, "outcome": new_status})
    db.commit()
    return tr.transfer_dict(t)
