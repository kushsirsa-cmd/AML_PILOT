from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    nationality: Mapped[str] = mapped_column(String(100))
    country_of_residence: Mapped[str] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(200))
    source_of_funds: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_of_wealth: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    annual_income: Mapped[float | None] = mapped_column(Float, nullable=True)  # EUR
    product: Mapped[str] = mapped_column(String(50), default="CURRENT_ACCOUNT")
    channel: Mapped[str] = mapped_column(String(50), default="FACE_TO_FACE")
    pep_declared: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(30), default="ONBOARDING", index=True)
    risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onboarded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_kyc_review: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_review_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    documents: Mapped[list[Document]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    hits: Mapped[list[ScreeningHit]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    reviews: Mapped[list[Review]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    assessments: Mapped[list[Assessment]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    notes: Mapped[list[CaseNote]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(40))  # ID_DOCUMENT, PROOF_OF_ADDRESS, SOF_EVIDENCE, SOW_EVIDENCE
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="documents")


class Assessment(Base):
    """Output of one agent run. History is kept; the latest row per (customer, agent) is current."""

    __tablename__ = "assessments"
    __table_args__ = (Index("ix_assessments_customer_agent", "customer_id", "agent"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String(30))
    engine: Mapped[str] = mapped_column(String(30), default="rules")  # rules | rules+claude
    output: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="assessments")


class ScreeningHit(Base):
    __tablename__ = "screening_hits"
    __table_args__ = (Index("ix_hits_customer_list_entity", "customer_id", "list_type", "entity_id", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    list_type: Mapped[str] = mapped_column(String(20))  # SANCTIONS | PEP | ADVERSE_MEDIA
    entity_id: Mapped[str] = mapped_column(String(60))
    matched_name: Mapped[str] = mapped_column(String(200))
    confidence: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    disposition: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | CONFIRMED | FALSE_POSITIVE
    disposition_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="hits")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    review_type: Mapped[str] = mapped_column(String(20))  # PERIODIC | EVENT_DRIVEN
    trigger: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING | COMPLETED | ESCALATED
    recommendation: Mapped[str | None] = mapped_column(String(80), nullable=True)
    outcome: Mapped[dict] = mapped_column(JSONType, default=dict)
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="reviews")


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String(30), default="rules")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped[Customer] = relationship(back_populates="notes")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_customer_ts", "customer_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(100))
    actor_type: Mapped[str] = mapped_column(String(10), index=True)  # USER | AI | SYSTEM
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # intentionally no FK: log outlives data
    details: Mapped[dict] = mapped_column(JSONType, default=dict)


# ---------------------------------------------------------------------------------------------
# Phase 2: KYB / UBO, crypto, travel rule, alerts, SAR, QA, regulatory reporting
# ---------------------------------------------------------------------------------------------
class Corporate(Base):
    __tablename__ = "corporates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corp_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    legal_name: Mapped[str] = mapped_column(String(250), index=True)
    registration_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    country_of_incorporation: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(50), default="LIMITED_COMPANY")
    industry: Mapped[str] = mapped_column(String(200))
    incorporation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    operating_countries: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma separated
    annual_turnover: Mapped[float | None] = mapped_column(Float, nullable=True)  # EUR
    employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    listed: Mapped[bool] = mapped_column(Boolean, default=False)
    has_bearer_shares: Mapped[bool] = mapped_column(Boolean, default=False)
    nominee_directors: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="ONBOARDING", index=True)
    risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OwnershipNode(Base):
    __tablename__ = "ownership_nodes"
    __table_args__ = (Index("ix_nodes_corp_key", "corporate_id", "node_key", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corporate_id: Mapped[int] = mapped_column(ForeignKey("corporates.id", ondelete="CASCADE"))
    node_key: Mapped[str] = mapped_column(String(60))  # local key, ROOT = the corporate itself
    name: Mapped[str] = mapped_column(String(250))
    node_type: Mapped[str] = mapped_column(String(10))  # PERSON | ENTITY
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. DIRECTOR
    id_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_listed: Mapped[bool] = mapped_column(Boolean, default=False)  # listed on a regulated exchange (exempt)
    is_trust: Mapped[bool] = mapped_column(Boolean, default=False)
    is_nominee: Mapped[bool] = mapped_column(Boolean, default=False)


class OwnershipEdge(Base):
    __tablename__ = "ownership_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corporate_id: Mapped[int] = mapped_column(ForeignKey("corporates.id", ondelete="CASCADE"), index=True)
    owner_key: Mapped[str] = mapped_column(String(60))
    owned_key: Mapped[str] = mapped_column(String(60))
    percentage: Mapped[float] = mapped_column(Float)
    control_type: Mapped[str] = mapped_column(String(20), default="SHARES")  # SHARES | VOTING | TRUST | NOMINEE


class Analysis(Base):
    """Generic stored output of a non-customer agent run (KYB, wallet screening, ...)."""

    __tablename__ = "analyses"
    __table_args__ = (Index("ix_analyses_entity", "entity_type", "entity_id", "kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))  # corporate | wallet
    entity_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))  # kyb | wallet_screening
    engine: Mapped[str] = mapped_column(String(30), default="rules")
    output: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (Index("ix_wallet_chain_addr", "chain", "address", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String(100))
    chain: Mapped[str] = mapped_column(String(10), default="ETH")
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    corporate_id: Mapped[int | None] = mapped_column(ForeignKey("corporates.id", ondelete="SET NULL"), nullable=True, index=True)
    hosted_by_vasp: Mapped[str | None] = mapped_column(String(150), nullable=True)
    self_hosted: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_screened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChainTx(Base):
    """Simulated blockchain ledger (stand-in for a Chainalysis / Elliptic / TRM data feed)."""

    __tablename__ = "chain_txs"
    __table_args__ = (Index("ix_chain_from", "from_address"), Index("ix_chain_to", "to_address"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tx_hash: Mapped[str] = mapped_column(String(80), unique=True)
    chain: Mapped[str] = mapped_column(String(10), default="ETH")
    from_address: Mapped[str] = mapped_column(String(100))
    to_address: Mapped[str] = mapped_column(String(100))
    asset: Mapped[str] = mapped_column(String(10))
    amount: Mapped[float] = mapped_column(Float)
    amount_eur: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AddressLabel(Base):
    """Attribution data: which entity/category an address belongs to."""

    __tablename__ = "address_labels"

    address: Mapped[str] = mapped_column(String(100), primary_key=True)
    chain: Mapped[str] = mapped_column(String(10), default="ETH")
    category: Mapped[str] = mapped_column(String(30), index=True)
    entity_name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(60), default="SIMULATED-ATTRIBUTION")


class TravelRuleTransfer(Base):
    __tablename__ = "travel_rule_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    corporate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wallet_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    direction: Mapped[str] = mapped_column(String(3))  # IN | OUT
    tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asset: Mapped[str] = mapped_column(String(10), default="USDT")
    amount_eur: Mapped[float] = mapped_column(Float)
    originator: Mapped[dict] = mapped_column(JSONType, default=dict)
    beneficiary: Mapped[dict] = mapped_column(JSONType, default=dict)
    counterparty_vasp: Mapped[str | None] = mapped_column(String(150), nullable=True)
    self_hosted: Mapped[bool] = mapped_column(Boolean, default=False)
    ownership_proof: Mapped[bool] = mapped_column(Boolean, default=False)
    checks: Mapped[list] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(30), index=True)  # ACCEPT | ACCEPT_WITH_REVIEW | HOLD_REQUEST_INFO | REJECT | NOT_APPLICABLE
    reasons: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30), index=True)  # CRYPTO | TRAVEL_RULE | KYB | CUSTOMER_RISK | SCREENING
    entity_type: Mapped[str] = mapped_column(String(20))  # customer | corporate | wallet | transfer
    entity_id: Mapped[int] = mapped_column(Integer)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(10))  # LOW | MEDIUM | HIGH | CRITICAL
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)  # OPEN|IN_REVIEW|ESCALATED_MLRO|SAR_DRAFTED|CLOSED
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sar_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Sar(Base):
    __tablename__ = "sars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True)
    subject_type: Mapped[str] = mapped_column(String(20))  # customer | corporate | wallet
    subject_id: Mapped[int] = mapped_column(Integer)
    subject_name: Mapped[str] = mapped_column(String(250))
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)  # DRAFT|PENDING_MLRO|APPROVED|REJECTED|FILED
    typologies: Mapped[list] = mapped_column(JSONType, default=list)
    evidence: Mapped[dict] = mapped_column(JSONType, default=dict)
    narrative: Mapped[str] = mapped_column(Text)
    engine: Mapped[str] = mapped_column(String(30), default="rules")
    total_amount_eur: Mapped[float] = mapped_column(Float, default=0)
    prepared_by: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mlro_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    filing_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QaReview(Base):
    __tablename__ = "qa_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_id: Mapped[int] = mapped_column(Integer, unique=True)  # the audit-log row (decision) under review
    decision_action: Mapped[str] = mapped_column(String(60), index=True)
    decision_maker: Mapped[str] = mapped_column(String(100), index=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(15), default="PENDING", index=True)  # PENDING | COMPLETED
    precheck: Mapped[list] = mapped_column(JSONType, default=list)  # automated findings
    checklist: Mapped[dict] = mapped_column(JSONType, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(25), nullable=True)  # PASS | PASS_WITH_FINDINGS | FAIL
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RegulatoryReport(Base):
    __tablename__ = "regulatory_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(15), default="DRAFT", index=True)  # DRAFT | APPROVED | SUBMITTED
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    generated_by: Mapped[str] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submission_reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(25))  # ANALYST | SENIOR_ANALYST | MLRO | COMPLIANCE_MANAGER | ADMIN
    email: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    """Fiat / account transactions used for transaction monitoring (crypto transfers live in chain_txs)."""

    __tablename__ = "transactions"
    __table_args__ = (Index("ix_txn_customer_ts", "customer_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    txn_ref: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    corporate_id: Mapped[int | None] = mapped_column(ForeignKey("corporates.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # IN | OUT
    amount_eur: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    channel: Mapped[str] = mapped_column(String(15))  # WIRE | CARD | CASH | SEPA | CRYPTO_OFFRAMP
    counterparty: Mapped[str] = mapped_column(String(160))
    counterparty_country: Mapped[str] = mapped_column(String(60))
    flags: Mapped[list] = mapped_column(JSONType, default=list)  # monitoring rules that fired


# ---------------------------------------------------------------------------------------------
# Phase 4: Investigations & FIU
# ---------------------------------------------------------------------------------------------
class EntityIdentifier(Base):
    """Contact / technical identifiers captured at onboarding and in session logs. Shared values across unrelated
    customers are the raw material of entity link analysis (shared phone / email / IP / device / wallet / bank account)."""

    __tablename__ = "entity_identifiers"
    __table_args__ = (Index("ix_ident_kind_value", "kind", "value"), Index("ix_ident_entity", "entity_type", "entity_id"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(10))  # customer | corporate
    entity_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(15))  # PHONE | EMAIL | IP | DEVICE | WALLET | BANK_ACCOUNT
    value: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(40), default="ONBOARDING")  # ONBOARDING | SESSION_LOG | PAYMENT_DATA


class Investigation(Base):
    """An investigation case. Moves through the queues ALERT -> TRIAGE -> FIU -> ESCALATION -> SAR -> MLRO -> CLOSED and
    through the nine-step investigation workflow (alert created ... closure decision)."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(250))
    source_type: Mapped[str] = mapped_column(String(15), default="ALERT")  # ALERT | RBI | FIU | MANUAL
    alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(10))  # customer | corporate
    entity_id: Mapped[int] = mapped_column(Integer)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(10), default="MEDIUM")  # LOW | MEDIUM | HIGH | CRITICAL
    queue: Mapped[str] = mapped_column(String(12), default="TRIAGE", index=True)  # TRIAGE|FIU|ESCALATION|SAR|MLRO|CLOSED
    step: Mapped[int] = mapped_column(Integer, default=2)  # 1..9 of the investigation workflow
    assigned_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    opened_by: Mapped[str] = mapped_column(String(100), default="system")
    escalated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # case confidence 0-100 (RBI agent)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # typology / network composite 0-100
    typologies: Mapped[list] = mapped_column(JSONType, default=list)
    agents: Mapped[dict] = mapped_column(JSONType, default=dict)  # latest output of each agent (rbi, fiu, typology, links, investigator, crypto)
    notes: Mapped[list] = mapped_column(JSONType, default=list)  # [{ts, author, text, kind}]
    disposition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    closure_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    sar_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
