"""Pydantic data models shared across pipeline stages."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LineRequest(BaseModel):
    """One product/service the customer asked about, as extracted from the email."""

    product_name: str = Field(description="Product or service name as the customer wrote it")
    quantity: Optional[Decimal] = Field(
        default=None, description="Requested quantity; null if not stated"
    )
    unit_hint: Optional[str] = Field(
        default=None, description="Unit the customer implied (seats, properties, days...)"
    )
    notes: Optional[str] = None


class RequestedTerms(BaseModel):
    payment_method: Optional[str] = None
    delivery_deadline: Optional[str] = Field(
        default=None, description="Deadline as stated, e.g. 'within 2 weeks'"
    )
    deadline_days: Optional[int] = Field(
        default=None, description="Deadline converted to days from now, if inferable"
    )
    discount_request_pct: Optional[Decimal] = Field(
        default=None, description="Discount the customer asked for, in percent"
    )
    other: list[str] = Field(default_factory=list)


class Inquiry(BaseModel):
    """Structured view of an inbound inquiry email (output of the intake stage)."""

    language: Literal["en", "zh"]
    contact_name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    subject: Optional[str] = None
    requests: list[LineRequest]
    requested_terms: RequestedTerms = Field(default_factory=RequestedTerms)
    questions: list[str] = Field(
        default_factory=list, description="Explicit questions the customer asked"
    )
    urgency: Literal["low", "normal", "high"] = "normal"
    summary: str = Field(description="One-sentence English summary of the inquiry")


class SellerInfo(BaseModel):
    name_en: str
    name_zh: str
    jurisdiction_en: str = ""
    jurisdiction_zh: str = ""
    website: str = ""
    email: str = ""
    description: str = Field(default="", description="One paragraph about the company")


class VolumeDiscount(BaseModel):
    min_qty: Decimal
    pct: Decimal


class CatalogItem(BaseModel):
    sku: str
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    unit: str
    unit_zh: str
    unit_price_usd: Decimal
    volume_discounts: list[VolumeDiscount] = Field(default_factory=list)


class FxRate(BaseModel):
    pair: str = "USD/CNY"
    rate: Decimal
    source: str
    as_of: str
    offline: bool = False


class PricedLine(BaseModel):
    sku: str
    name_en: str
    name_zh: str
    unit: str
    unit_zh: str
    quantity: Decimal
    unit_price_usd: Decimal
    discount_pct: Decimal = Decimal("0")
    line_total_usd: Decimal
    line_total_cny: Decimal
    note: Optional[str] = None


class UnmatchedRequest(BaseModel):
    product_name: str
    reason: str


class RiskFlag(BaseModel):
    code: str
    severity: Literal["info", "warn", "block"]
    message_en: str
    message_zh: str


class CoverLetters(BaseModel):
    """LLM-drafted personalized text (the only LLM-authored part of the quote)."""

    cover_letter_en: str
    cover_letter_zh: str
    answers_en: str = Field(description="Answers to the customer's questions, English")
    answers_zh: str = Field(description="Answers to the customer's questions, Chinese")


class Customer(BaseModel):
    contact_name: str = "—"
    company: str = "—"
    email: str = "—"


class QuoteDraft(BaseModel):
    quote_number: str
    seller: SellerInfo
    issue_date: date
    valid_until: date
    customer: Customer
    lines: list[PricedLine]
    unmatched: list[UnmatchedRequest] = Field(default_factory=list)
    subtotal_usd: Decimal
    discount_usd: Decimal
    total_usd: Decimal
    total_cny: Decimal
    fx: FxRate
    cover: CoverLetters
    payment_terms_en: str
    payment_terms_zh: str
    legal_en: str
    legal_zh: str
    extra_notes_en: list[str] = Field(default_factory=list)
    extra_notes_zh: list[str] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    notes: Optional[str] = None
    decided_at: datetime


class RunResult(BaseModel):
    run_id: str
    decision: Decision
    quote: QuoteDraft
    artifacts: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, dict[str, int]] = Field(default_factory=dict)
