"""Framework-agnostic pipeline core: assemble a quote draft, render artifacts.

Used by both the classic orchestrator (CLI/web) and the AgentScope agent path.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import config, llm
from .models import Customer, Inquiry, QuoteDraft
from .stages import drafting, fx, intake, pricing, render, risk


def new_quote_number() -> str:
    return f"LUQ-Q-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2).upper()}"


def assemble_quote_draft(
    raw_email: str,
    usage: llm.UsageTracker | None = None,
    on_stage=None,
) -> tuple[QuoteDraft, "Inquiry"]:
    """Run stages intake → fx → pricing → risk → drafting; return (draft, inquiry)."""

    def note(stage: str) -> None:
        if on_stage:
            on_stage(stage)

    inquiry = intake.parse_inquiry(raw_email, usage)
    note("intake")
    rate = fx.get_usd_cny()
    note("fx")
    lines, unmatched = pricing.price_inquiry(inquiry, rate, usage)
    subtotal, discount, total, total_cny = pricing.totals(lines, rate)
    note("pricing")
    flags = risk.rule_flags(inquiry, lines, unmatched, total, raw_email)
    note("risk_rules")
    flags += risk.llm_sweep(raw_email, inquiry, usage)
    note("risk_llm_sweep")
    cover = drafting.draft_cover(inquiry, lines, flags, usage)
    note("drafting")

    today = date.today()
    extra_en, extra_zh = [], []
    if any(f.code == "FAPIAO_REQUEST" for f in flags):
        extra_en.append(config.TERMS["tax_note_en"])
        extra_zh.append(config.TERMS["tax_note_zh"])

    quote = QuoteDraft(
        quote_number=new_quote_number(),
        issue_date=today,
        valid_until=today + timedelta(days=config.QUOTE_VALIDITY_DAYS),
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
        payment_terms_en=config.TERMS["payment_en"],
        payment_terms_zh=config.TERMS["payment_zh"],
        legal_en=config.TERMS["legal_en"],
        legal_zh=config.TERMS["legal_zh"],
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
