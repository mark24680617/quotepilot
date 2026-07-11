"""Intake stage: parse a raw inquiry email into a structured Inquiry (qwen-flash)."""

from __future__ import annotations

from .. import config, llm
from ..models import Inquiry
from ..profile import CompanyProfile

_SYSTEM = """You are the intake analyst of {seller_name} ({seller_desc}), which sells
to business customers cross-border. You read inbound inquiry emails written in
English or Chinese and extract a faithful, structured summary.

Rules:
- NEVER invent data. If a quantity, name, or term is not stated, leave it null
  and record the ambiguity as a question to clarify.
- EVERY distinct product or service gets its OWN entry in requests — even when
  mentioned in the same sentence ("80 seats plus your onboarding service" is
  TWO requests). Never fold a requested service into another item's notes.
- A clearly requested one-time service (onboarding, integration, setup) with
  no stated quantity has quantity 1.
- language = the primary language of the email body ("en" or "zh").
- quantity is a number only (no units); put the unit words in unit_hint.
- discount_request_pct: only if the customer explicitly asked for a discount
  with a number; a vague "best price" goes into requested_terms.other.
- deadline_days: convert explicit deadlines ("within 2 weeks") to integer days;
  if no deadline stated, null.
- urgency: high only if the customer signals time pressure explicitly.
- questions: every explicit question the customer asked, in the original language.
- summary: one English sentence."""


def parse_inquiry(
    raw_email: str,
    profile: CompanyProfile,
    usage: llm.UsageTracker | None = None,
) -> Inquiry:
    system = _SYSTEM.format(
        seller_name=profile.seller.name_en,
        seller_desc=profile.seller.description or "a B2B seller",
    )
    return llm.structured(
        config.WORKER_MODEL,
        system,
        f"Inbound email:\n---\n{raw_email}\n---",
        Inquiry,
        usage=usage,
        max_tokens=1500,
    )
