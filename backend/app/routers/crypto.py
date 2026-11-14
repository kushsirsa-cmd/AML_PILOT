from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import current_user
from ..models import AddressLabel, ChainTx, Corporate, Customer, Wallet
from ..modules import chain, wallets as wsvc

router = APIRouter(prefix="/api/crypto", tags=["crypto"])


class WalletIn(BaseModel):
    address: str = Field(min_length=10, max_length=100)
    chain: str = "ETH"
    label: str | None = None
    customer_id: int | None = None
    corporate_id: int | None = None
    self_hosted: bool = True
    hosted_by_vasp: str | None = None
    screen: bool = True


class AddressIn(BaseModel):
    address: str = Field(min_length=10)


def wdict(db: Session, w: Wallet) -> dict:
    owner = None
    if w.customer_id and (c := db.get(Customer, w.customer_id)):
        owner = dict(type="customer", id=c.id, name=c.full_name, ref=c.customer_ref)
    elif w.corporate_id and (c2 := db.get(Corporate, w.corporate_id)):
        owner = dict(type="corporate", id=c2.id, name=c2.legal_name, ref=c2.corp_ref)
    return dict(id=w.id, address=w.address, chain=w.chain, label=w.label, owner=owner, self_hosted=w.self_hosted, hosted_by_vasp=w.hosted_by_vasp,
                risk_score=w.risk_score, risk_level=w.risk_level, last_screened_at=w.last_screened_at.isoformat() if w.last_screened_at else None)


def get_wallet(wallet_id: int, db: Session = Depends(get_db)) -> Wallet:
    w = db.get(Wallet, wallet_id)
    if not w:
        raise HTTPException(404, "Wallet not found")
    return w


@router.get("/wallets")
def list_wallets(db: Session = Depends(get_db)):
    return [wdict(db, w) for w in db.scalars(select(Wallet).order_by(Wallet.risk_score.desc().nullslast(), Wallet.id))]


@router.post("/wallets", status_code=201)
def add_wallet(body: WalletIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    if db.scalar(select(Wallet).where(Wallet.address == body.address, Wallet.chain == body.chain)):
        raise HTTPException(409, "Wallet already registered")
    if body.customer_id and not db.get(Customer, body.customer_id):
        raise HTTPException(404, "Customer not found")
    if body.corporate_id and not db.get(Corporate, body.corporate_id):
        raise HTTPException(404, "Corporate not found")
    w = Wallet(**body.model_dump(exclude={"screen"}))
    db.add(w)
    db.flush()
    audit.log(db, actor=user, actor_type=audit.USER, action="WALLET_REGISTERED", entity_type="wallet", entity_id=w.id, customer_id=w.customer_id,
              details={"address": w.address})
    if body.screen:
        wsvc.screen_wallet(db, w, actor=user)
        wsvc.refresh_customer_risk(db, w.customer_id, user)
    db.commit()
    return get_wallet_detail(w, db)


@router.get("/wallets/{wallet_id}")
def get_wallet_detail(w: Wallet = Depends(get_wallet), db: Session = Depends(get_db)):
    return dict(wallet=wdict(db, w), screening=wsvc.latest_screening(db, w.id))


@router.post("/wallets/{wallet_id}/screen")
def screen(w: Wallet = Depends(get_wallet), db: Session = Depends(get_db), user: str = Depends(current_user)):
    wsvc.screen_wallet(db, w, actor=user)
    wsvc.refresh_customer_risk(db, w.customer_id, user)
    db.commit()
    return get_wallet_detail(w, db)


@router.get("/wallets/{wallet_id}/analysis")
def tx_analysis(w: Wallet = Depends(get_wallet), db: Session = Depends(get_db), hops: int = Query(2, ge=1, le=3)):
    """Chainalysis-Reactor-style investigation view: timeline, counterparties, graph, risky traces and patterns."""
    g = chain.ChainGraph.load(db)
    txs = sorted(g.inn.get(w.address, []) + g.out.get(w.address, []), key=lambda t: chain.aware(t.ts))
    daily: dict[str, dict] = {}
    for t in txs:
        d = chain.aware(t.ts).date().isoformat()
        row = daily.setdefault(d, dict(date=d, inbound_eur=0.0, outbound_eur=0.0, tx_count=0))
        row["inbound_eur" if t.to_address == w.address else "outbound_eur"] += t.amount_eur
        row["tx_count"] += 1
    res = chain.screen_address(g, w.address)
    return dict(
        wallet=wdict(db, w), summary=dict(tx_count=len(txs), first_seen=chain.aware(txs[0].ts).isoformat() if txs else None,
                                          last_seen=chain.aware(txs[-1].ts).isoformat() if txs else None, **{k: res["exposure"][k] for k in ("total_received_eur", "total_sent_eur")}),
        risk=dict(score=res["risk_score"], level=res["risk_level"], components=res["score_components"], overrides=res["overrides"]),
        exposure=res["exposure"], patterns=res["patterns"], risky_traces=res["risky_traces"], counterparties=g.counterparties(w.address),
        graph=g.subgraph(w.address, hops=hops), daily=[daily[k] for k in sorted(daily)],
        transactions=[dict(tx_hash=t.tx_hash, ts=chain.aware(t.ts).isoformat(), direction="IN" if t.to_address == w.address else "OUT",
                           counterparty=t.from_address if t.to_address == w.address else t.to_address,
                           counterparty_category=g.category(t.from_address if t.to_address == w.address else t.to_address),
                           counterparty_entity=(g.labels[a].entity_name if (a := (t.from_address if t.to_address == w.address else t.to_address)) in g.labels else None),
                           asset=t.asset, amount=t.amount, amount_eur=t.amount_eur) for t in txs],
    )


@router.post("/screen")
def screen_adhoc(body: AddressIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Screen any address on the simulated chain without registering it."""
    g = chain.ChainGraph.load(db)
    if body.address not in g.inn and body.address not in g.out and body.address not in g.labels:
        raise HTTPException(404, "Address not seen on the simulated chain. Use one from /api/crypto/labels or a registered wallet.")
    res = chain.screen_address(g, body.address)
    audit.log(db, actor=user, actor_type=audit.USER, action="ADHOC_WALLET_SCREENING", entity_type="wallet",
              details={"address": body.address, "level": res["risk_level"], "score": res["risk_score"]})
    db.commit()
    return res


@router.get("/labels")
def labels(db: Session = Depends(get_db)):
    return [dict(address=l.address, category=l.category, entity=l.entity_name, source=l.source) for l in db.scalars(select(AddressLabel).order_by(AddressLabel.category))]


@router.get("/transactions")
def transactions(address: str | None = None, limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    stmt = select(ChainTx).order_by(ChainTx.ts.desc()).limit(limit)
    if address:
        stmt = stmt.where(or_(ChainTx.from_address == address, ChainTx.to_address == address))
    return [dict(tx_hash=t.tx_hash, from_address=t.from_address, to_address=t.to_address, asset=t.asset, amount=t.amount, amount_eur=t.amount_eur,
                 ts=chain.aware(t.ts).astimezone(timezone.utc).isoformat()) for t in db.scalars(stmt)]
