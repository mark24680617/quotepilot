"""Drafting stage: qwen-max writes the personalized bilingual cover text.

Only the cover letters and question answers are LLM-authored. Prices, terms,
and legal language are fixed by code and templates.
"""

from __future__ import annotations

import json

from .. import config, llm
from ..profile import CompanyProfile
from ..models import CoverLetters, Inquiry, PricedLine, RiskFlag

_SYSTEM = """You draft the personalized text of a formal B2B price quote for
{seller_name} ({seller_jurisdiction}), selling cross-border to Chinese
enterprise customers. Write BOTH English and Simplified Chinese versions.

Style: professional, warm, concise. The Chinese version must read like native
business Chinese (商务中文), not a translation. Do NOT quote any prices or
totals in the letters (the quote table shows them). Do NOT invent commitments,
discounts, or delivery dates. Do NOT write legal terms — those are fixed.

cover_letter_en / cover_letter_zh: 2-3 short paragraphs thanking them,
confirming what was quoted, and a clear next step (reply to confirm; we then
issue the Stripe invoice or wire instructions and the bilingual contract).

answers_en / answers_zh: directly answer each question the customer asked,
faithfully to the provided facts. If a question cannot be answered from the
facts, say it will be confirmed by the account manager. If there are no
questions, return an empty string for both."""


def draft_cover(
    inquiry: Inquiry,
    lines: list[PricedLine],
    flags: list[RiskFlag],
    profile: CompanyProfile,
    usage: llm.UsageTracker | None = None,
) -> CoverLetters:
    facts = {
        "customer": {
            "contact_name": inquiry.contact_name,
            "company": inquiry.company,
            "language": inquiry.language,
        },
        "quoted_items": [
            {"name_en": l.name_en, "name_zh": l.name_zh, "qty": str(l.quantity), "unit": l.unit}
            for l in lines
        ],
        "customer_questions": inquiry.questions,
        "risk_context": [f.message_en for f in flags if f.severity != "info"],
        "fixed_facts": {
            "payment": profile.terms.payment_en,
            "tax": profile.terms.tax_note_en,
            "legal": profile.terms.legal_en,
            "validity_days": profile.rules.quote_validity_days,
        },
    }
    system = _SYSTEM.format(
        seller_name=profile.seller.name_en,
        seller_jurisdiction=profile.seller.jurisdiction_en or "a company",
    )
    cover = llm.structured(
        config.PLANNER_MODEL,
        system,
        "Facts:\n" + json.dumps(facts, ensure_ascii=False, indent=1),
        CoverLetters,
        usage=usage,
        temperature=0.5,
        max_tokens=2500,
    )
    # Models sometimes double-escape newlines inside JSON strings.
    for field in ("cover_letter_en", "cover_letter_zh", "answers_en", "answers_zh"):
        setattr(cover, field, getattr(cover, field).replace("\\n", "\n").strip())
    return cover
