"""Risk stage: deterministic business rules + a Qwen sanity sweep.

Rule flags are authoritative; the LLM sweep can only ADD advisory flags,
never remove rule-based ones.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .. import config, llm
from ..profile import CompanyProfile
from ..models import Inquiry, PricedLine, RiskFlag, UnmatchedRequest

_FAPIAO_TOKENS = ("发票", "增值税", "fapiao", "vat invoice")
_JURISDICTION_TOKENS = ("中国法院", "国内法院", "chinese court", "prc court", "中国仲裁")


def rule_flags(
    inquiry: Inquiry,
    lines: list[PricedLine],
    unmatched: list[UnmatchedRequest],
    total_usd: Decimal,
    raw_email: str,
    profile: CompanyProfile,
) -> list[RiskFlag]:
    rules = profile.rules
    flags: list[RiskFlag] = []
    lowered = raw_email.lower()

    if not lines:
        flags.append(
            RiskFlag(
                code="NO_PRICEABLE_LINES",
                severity="block",
                message_en="No request could be priced — human must handle this inquiry.",
                message_zh="没有可报价的条目——需人工处理该询价。",
            )
        )
    for miss in unmatched:
        flags.append(
            RiskFlag(
                code="UNMATCHED_REQUEST",
                severity="warn",
                message_en=f"'{miss.product_name}': {miss.reason}",
                message_zh=f"“{miss.product_name}”:{miss.reason}",
            )
        )

    if total_usd >= rules.wire_threshold_usd:
        flags.append(
            RiskFlag(
                code="WIRE_RECOMMENDED",
                severity="info",
                message_en=(
                    f"Order total USD {total_usd:,} exceeds {rules.wire_threshold_usd:,} — "
                    "recommend wire transfer and China outbound-payment tax filing."
                ),
                message_zh=(
                    f"订单总额 {total_usd:,} 美元超过 {rules.wire_threshold_usd:,} 美元——"
                    "建议采用电汇并办理对外支付税务备案。"
                ),
            )
        )

    req_pct = inquiry.requested_terms.discount_request_pct
    if req_pct is not None and req_pct > rules.max_extra_discount_pct:
        flags.append(
            RiskFlag(
                code="DISCOUNT_ABOVE_FLOOR",
                severity="warn",
                message_en=(
                    f"Customer asked for {req_pct}% discount; policy floor is "
                    f"{rules.max_extra_discount_pct}%. Quote applies volume tiers only — "
                    "extra discount needs management approval."
                ),
                message_zh=(
                    f"客户要求 {req_pct}% 折扣;政策底线为 {rules.max_extra_discount_pct}%。"
                    "本报价仅按数量阶梯折扣——额外折扣需管理层批准。"
                ),
            )
        )

    days = inquiry.requested_terms.deadline_days
    if days is not None and days <= rules.urgent_deadline_days:
        flags.append(
            RiskFlag(
                code="TIGHT_DEADLINE",
                severity="warn",
                message_en=f"Customer deadline ≈{days} days — confirm delivery capacity before sending.",
                message_zh=f"客户交付期限约 {days} 天——发送前请确认交付能力。",
            )
        )

    if any(tok in lowered or tok in raw_email for tok in _FAPIAO_TOKENS):
        flags.append(
            RiskFlag(
                code="FAPIAO_REQUEST",
                severity="warn",
                message_en="Customer mentioned Chinese VAT fapiao — US entity cannot issue one; tax note added to quote.",
                message_zh="客户提及增值税发票——美国主体无法开具;报价单已附税务说明。",
            )
        )

    if any(tok in lowered or tok in raw_email for tok in _JURISDICTION_TOKENS):
        flags.append(
            RiskFlag(
                code="JURISDICTION_CONFLICT",
                severity="warn",
                message_en="Customer suggested PRC courts/arbitration — conflicts with our HKIAC standard terms.",
                message_zh="客户提出中国法院/仲裁管辖——与我方 HKIAC 标准条款冲突。",
            )
        )
    return flags


class _LLMFlag(BaseModel):
    code: str = Field(description="SHORT_SNAKE_CASE code")
    severity: str = Field(description="info or warn")
    message_en: str
    message_zh: str


class _LLMFlags(BaseModel):
    flags: list[_LLMFlag] = Field(default_factory=list)


def llm_sweep(
    raw_email: str,
    inquiry: Inquiry,
    profile: CompanyProfile,
    usage: llm.UsageTracker | None = None,
) -> list[RiskFlag]:
    """Ask qwen-flash for anything unusual the rules missed. Advisory only."""
    try:
        result = llm.structured(
            config.WORKER_MODEL,
            f"You are a cross-border B2B deal-desk reviewer for {profile.seller.name_en} "
            "whose NORMAL customer base is mainland-Chinese companies. Given an "
            "inquiry email and its extraction, list only UNUSUAL, high-signal "
            "commercial/legal/compliance concerns a rules engine might miss "
            "(explicit resale/white-label hints, data-residency or on-prem demands, "
            "government/military end use, technically impossible asks). Being a "
            "Chinese company, paying from China, or ordinary volume purchases are "
            "NOT concerns — never flag those. Most inquiries deserve an empty list. "
            "Max 2 flags. severity must be 'info' or 'warn'.",
            f"Email:\n{raw_email}\n\nExtraction summary: {inquiry.summary}",
            _LLMFlags,
            usage=usage,
            max_tokens=800,
        )
    except RuntimeError:
        return []  # advisory sweep must never break the pipeline
    out: list[RiskFlag] = []
    for f in result.flags[:3]:
        sev = f.severity if f.severity in ("info", "warn") else "info"
        out.append(
            RiskFlag(
                code=f"LLM_{f.code[:40]}",
                severity=sev,  # type: ignore[arg-type]
                message_en=f.message_en,
                message_zh=f.message_zh,
            )
        )
    return out
