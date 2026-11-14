from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

PRODUCTS = ["CURRENT_ACCOUNT", "SAVINGS", "CREDIT_CARD", "MORTGAGE", "INVESTMENT", "INTERNATIONAL_WIRES",
            "PRIVATE_BANKING", "TRADE_FINANCE", "CORRESPONDENT", "CRYPTO_CUSTODY"]
CHANNELS = ["FACE_TO_FACE", "ONLINE", "INTERMEDIARY", "REMOTE_NO_ID_CHECK"]


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    date_of_birth: date
    nationality: str = Field(min_length=2, max_length=100)
    country_of_residence: str = Field(min_length=2, max_length=100)
    address: str | None = None
    occupation: str = Field(min_length=2, max_length=200)
    industry: str = Field(min_length=2, max_length=200)
    source_of_funds: str | None = None
    source_of_wealth: str | None = None
    expected_activity: str | None = None
    annual_income: float | None = Field(default=None, ge=0)
    product: str = "CURRENT_ACCOUNT"
    channel: str = "FACE_TO_FACE"
    pep_declared: bool = False

    @field_validator("product")
    @classmethod
    def _product(cls, v: str) -> str:
        if v not in PRODUCTS:
            raise ValueError(f"product must be one of {PRODUCTS}")
        return v

    @field_validator("channel")
    @classmethod
    def _channel(cls, v: str) -> str:
        if v not in CHANNELS:
            raise ValueError(f"channel must be one of {CHANNELS}")
        return v

    @field_validator("full_name", "nationality", "country_of_residence", "occupation", "industry")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class CustomerUpdate(BaseModel):
    full_name: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    country_of_residence: str | None = None
    address: str | None = None
    occupation: str | None = None
    industry: str | None = None
    source_of_funds: str | None = None
    source_of_wealth: str | None = None
    expected_activity: str | None = None
    annual_income: float | None = Field(default=None, ge=0)
    product: str | None = None
    channel: str | None = None
    pep_declared: bool | None = None


class DocumentIn(BaseModel):
    doc_type: Literal["ID_DOCUMENT", "PROOF_OF_ADDRESS", "SOF_EVIDENCE", "SOW_EVIDENCE"]
    description: str | None = None
    issued_date: date | None = None
    expiry_date: date | None = None


class DecisionIn(BaseModel):
    decision: Literal["APPROVE", "REJECT", "ESCALATE", "REQUEST_INFO"]
    note: str = Field(min_length=3)


class ReviewDecisionIn(BaseModel):
    decision: Literal["COMPLETE_NO_CHANGE", "COMPLETE_WITH_UPDATES", "ESCALATE", "EXIT_RELATIONSHIP"]
    note: str = Field(min_length=3)


class DispositionIn(BaseModel):
    disposition: Literal["OPEN", "CONFIRMED", "FALSE_POSITIVE"]
    note: str | None = None


class EventIn(BaseModel):
    event_type: Literal["ADDRESS_CHANGE", "NEW_SANCTIONS_MATCH", "OCCUPATION_CHANGE", "NEW_ADVERSE_MEDIA"]
    payload: dict = Field(default_factory=dict)


class AdhocScreenIn(BaseModel):
    name: str = Field(min_length=2)
    date_of_birth: date | None = None
    nationality: str | None = None
