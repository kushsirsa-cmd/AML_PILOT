from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user
from ..models import Alert, Analysis, Corporate, OwnershipEdge, OwnershipNode, Wallet
from ..modules import kyb, ownership

router = APIRouter(prefix="/api/kyb", tags=["kyb"])


class NodeIn(BaseModel):
    key: str = Field(min_length=1, max_length=60)
    name: str
    node_type: str = "PERSON"
    country: str | None = None
    dob: str | None = None
    role: str | None = None
    id_verified: bool = False
    verification_note: str | None = None
    is_listed: bool = False
    is_trust: bool = False
    is_nominee: bool = False


class EdgeIn(BaseModel):
    owner: str
    owned: str
    percentage: float = Field(gt=0, le=100)
    control_type: str = "SHARES"


class StructureIn(BaseModel):
    nodes: list[NodeIn] = []
    edges: list[EdgeIn] = []


class CorporateIn(BaseModel):
    legal_name: str = Field(min_length=2)
    registration_number: str | None = None
    country_of_incorporation: str
    entity_type: str = "LIMITED_COMPANY"
    industry: str
    incorporation_date: date | None = None
    registered_address: str | None = None
    operating_countries: str | None = None
    annual_turnover: float | None = Field(default=None, ge=0)
    employees: int | None = Field(default=None, ge=0)
    expected_activity: str | None = None
    listed: bool = False
    has_bearer_shares: bool = False
    nominee_directors: bool = False
    structure: StructureIn | None = None
    run_review: bool = True


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|ESCALATE|REQUEST_INFO)$")
    note: str = Field(min_length=3)


def corp_dict(c: Corporate) -> dict:
    return {k: (v.isoformat() if isinstance(v, (date,)) else v) for k, v in {
        "id": c.id, "corp_ref": c.corp_ref, "legal_name": c.legal_name, "registration_number": c.registration_number,
        "country_of_incorporation": c.country_of_incorporation, "entity_type": c.entity_type, "industry": c.industry,
        "incorporation_date": c.incorporation_date, "registered_address": c.registered_address, "operating_countries": c.operating_countries,
        "annual_turnover": c.annual_turnover, "employees": c.employees, "expected_activity": c.expected_activity, "listed": c.listed,
        "has_bearer_shares": c.has_bearer_shares, "nominee_directors": c.nominee_directors, "status": c.status,
        "risk_rating": c.risk_rating, "risk_score": c.risk_score}.items()}


def get_corp(corp_id: int, db: Session = Depends(get_db)) -> Corporate:
    c = db.get(Corporate, corp_id)
    if not c:
        raise HTTPException(404, "Corporate not found")
    return c


def detail(db: Session, c: Corporate) -> dict:
    nodes, edges = kyb.load_structure(db, c)
    a = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == c.id, Analysis.kind == "kyb").order_by(Analysis.id.desc()).limit(1))
    wallets = db.scalars(select(Wallet).where(Wallet.corporate_id == c.id)).all()
    alerts = db.scalars(select(Alert).where(Alert.entity_type == "corporate", Alert.entity_id == c.id).order_by(Alert.id.desc())).all()
    return {
        "corporate": corp_dict(c),
        "structure": {
            "nodes": [dict(key=n.node_key, name=n.name, node_type=n.node_type, country=n.country, dob=n.dob.isoformat() if n.dob else None, role=n.role,
                           id_verified=n.id_verified, verification_note=n.verification_note, is_listed=n.is_listed, is_trust=n.is_trust,
                           is_nominee=n.is_nominee) for n in nodes if n.node_key != "ROOT"],
            "edges": [dict(owner=e.owner_key, owned=e.owned_key, percentage=e.percentage, control_type=e.control_type) for e in edges],
        },
        "review": a.output if a else None,
        "review_at": a.created_at.isoformat() if a else None,
        "wallets": [dict(id=w.id, address=w.address, chain=w.chain, risk_level=w.risk_level, risk_score=w.risk_score) for w in wallets],
        "alerts": [dict(id=x.id, title=x.title, severity=x.severity, status=x.status) for x in alerts],
    }


@router.get("/corporates")
def list_corporates(db: Session = Depends(get_db)):
    return [corp_dict(c) for c in db.scalars(select(Corporate).order_by(Corporate.id.desc()))]


@router.post("/corporates", status_code=201)
def create_corporate(body: CorporateIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    data = body.model_dump(exclude={"structure", "run_review"})
    c = Corporate(corp_ref="TMP", **data)
    db.add(c)
    db.flush()
    c.corp_ref = f"CORP-{c.id:05d}"
    audit.log(db, actor=user, actor_type=audit.USER, action="CORPORATE_CREATED", entity_type="corporate", entity_id=c.id, details={"name": c.legal_name})
    try:
        kyb.replace_structure(db, c, [n.model_dump() for n in body.structure.nodes] if body.structure else [],
                              [e.model_dump() for e in body.structure.edges] if body.structure else [])
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    if body.run_review:
        kyb.run(db, c, actor=user)
    db.commit()
    return detail(db, c)


@router.get("/corporates/{corp_id}")
def get_corporate(c: Corporate = Depends(get_corp), db: Session = Depends(get_db)):
    return detail(db, c)


@router.put("/corporates/{corp_id}/structure")
def put_structure(body: StructureIn, rerun: bool = True, c: Corporate = Depends(get_corp), db: Session = Depends(get_db), user: str = Depends(current_user)):
    try:
        kyb.replace_structure(db, c, [n.model_dump() for n in body.nodes], [e.model_dump() for e in body.edges])
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    audit.log(db, actor=user, actor_type=audit.USER, action="OWNERSHIP_STRUCTURE_UPDATED", entity_type="corporate", entity_id=c.id,
              details={"nodes": len(body.nodes), "edges": len(body.edges)})
    if rerun:
        kyb.run(db, c, actor=user)
    db.commit()
    return detail(db, c)


@router.post("/corporates/{corp_id}/review")
def run_review(c: Corporate = Depends(get_corp), db: Session = Depends(get_db), user: str = Depends(current_user)):
    kyb.run(db, c, actor=user)
    db.commit()
    return detail(db, c)


@router.post("/corporates/{corp_id}/decision")
def decide(body: DecisionIn, c: Corporate = Depends(get_corp), db: Session = Depends(get_db), user: str = Depends(current_user)):
    a = db.scalar(select(Analysis).where(Analysis.entity_type == "corporate", Analysis.entity_id == c.id, Analysis.kind == "kyb").order_by(Analysis.id.desc()).limit(1))
    if body.decision == "APPROVE":
        if not a:
            raise HTTPException(409, "Run the KYB review before approving.")
        if c.risk_rating == "PROHIBITED":
            raise HTTPException(409, "Corporates rated PROHIBITED cannot be approved.")
        if a.output["ubo_status"] != "VERIFIED":
            raise HTTPException(409, f"UBO verification is {a.output['ubo_status']}: all beneficial owners must be identified and verified before approval.")
    old = c.status
    c.status = {"APPROVE": "ACTIVE", "REJECT": "REJECTED", "ESCALATE": "UNDER_REVIEW", "REQUEST_INFO": "ONBOARDING"}[body.decision]
    audit.log(db, actor=user, actor_type=audit.USER, action="KYB_DECISION", entity_type="corporate", entity_id=c.id,
              details={"decision": body.decision, "note": body.note, "status_from": old, "status_to": c.status, "risk_rating": c.risk_rating})
    db.commit()
    return detail(db, c)


@router.post("/ownership/analyze")
def analyze_adhoc(body: CorporateIn):
    """Stateless ownership / UBO analysis of a structure (nothing is stored)."""
    corp = Corporate(legal_name=body.legal_name, country_of_incorporation=body.country_of_incorporation, industry=body.industry,
                     has_bearer_shares=body.has_bearer_shares, nominee_directors=body.nominee_directors)
    st = body.structure or StructureIn()
    nodes = [OwnershipNode(node_key="ROOT", name=body.legal_name, node_type="ENTITY", country=body.country_of_incorporation)]
    for n in st.nodes:
        nodes.append(OwnershipNode(node_key=n.key, name=n.name, node_type=n.node_type, country=n.country,
                                   dob=date.fromisoformat(n.dob) if n.dob else None, role=n.role, id_verified=n.id_verified, is_listed=n.is_listed,
                                   is_trust=n.is_trust, is_nominee=n.is_nominee))
    edges = [OwnershipEdge(owner_key=e.owner, owned_key=e.owned, percentage=e.percentage, control_type=e.control_type) for e in st.edges]
    return ownership.analyze(corp, nodes, edges)
