"""Framework-agnostic pipeline core: assemble a quote draft, render artifacts.

Used by both the classic orchestrator (CLI/web) and the AgentScope agent path.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import llm
from .models import Customer, Inquiry, QuoteDraft
from .profile import CompanyProfile, load_profile
from .stages import drafting, fx, intake, pricing, render, risk


def new_quote_number(prefix: str) -> str:
    return f"{prefix}-Q-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2).upper()}"


def assemble_quote_draft(
    raw_email: str,
    usage: llm.UsageTracker | None = None,
    on_stage=None,
) -> tuple[QuoteDraft, "Inquiry"]:
    """Run stages intake → fx → pricing → risk → drafting; return (draft, inquiry)."""

    def note(stage: str) -> None:
        if on_stage:
            on_stage(stage)

    profile = load_profile()
    inquiry = intake.parse_inquiry(raw_email, profile, usage)
    note("intake")
    rate = fx.get_usd_cny()
    note("fx")
    lines, unmatched = pricing.price_inquiry(inquiry, rate, profile, usage)
    subtotal, discount, total, total_cny = pricing.totals(lines, rate)
    note("pricing")
    flags = risk.rule_flags(inquiry, lines, unmatched, total, raw_email, profile)
    note("risk_rules")
    flags += risk.llm_sweep(raw_email, inquiry, profile, usage)
    note("risk_llm_sweep")
    cover = drafting.draft_cover(inquiry, lines, flags, profile, usage)
    note("drafting")

    today = date.today()
    extra_en, extra_zh = [], []
    if any(f.code == "FAPIAO_REQUEST" for f in flags) and profile.terms.tax_note_en:
        extra_en.append(profile.terms.tax_note_en)
        extra_zh.append(profile.terms.tax_note_zh)

    quote = QuoteDraft(
        quote_number=new_quote_number(profile.rules.quote_prefix),
        seller=profile.seller,
        issue_date=today,
        valid_until=today + timedelta(days=profile.rules.quote_validity_days),
        customer=Customer(
            contact_name=inquiry.contact_name or "—",
            company=inquiry.company or "—",
            email=inquiry.email or "—",
        ),
        lines=lines,
        unmatched=unmatched,
        subtotal_usd=subtotal,
        discount_usd=discount,
        total_usd=total,
        total_cny=total_cny,
        fx=rate,
        cover=cover,
        payment_terms_en=profile.terms.payment_en,
        payment_terms_zh=profile.terms.payment_zh,
        legal_en=profile.terms.legal_en,
        legal_zh=profile.terms.legal_zh,
        extra_notes_en=extra_en,
        extra_notes_zh=extra_zh,
        risk_flags=flags,
    )
    return quote, inquiry


def render_artifacts(quote: QuoteDraft, run_dir: Path) -> dict[str, str]:
    """Write approved-quote artifacts; returns kind -> absolute path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    html_path = run_dir / f"{quote.quote_number}.html"
    html_path.write_text(render.render_quote_html(quote), encoding="utf-8")
    email_path = run_dir / "reply_email.md"
    email_path.write_text(render.render_reply_email(quote), encoding="utf-8")
    quote_json = run_dir / "quote.json"
    quote_json.write_text(quote.model_dump_json(indent=2), encoding="utf-8")
    return {
        "quote_html": str(html_path),
        "reply_email": str(email_path),
        "quote_json": str(quote_json),
    }
