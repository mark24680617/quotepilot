"""Framework-agnostic pipeline core: assemble a quote draft, render artifacts.

Used by both the classic orchestrator (CLI/web) and the AgentScope agent path.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from . import llm
from .models import Customer, Inquiry, PricedLine, QuoteDraft
from .profile import CompanyProfile, load_profile
from .stages import drafting, fx, intake, pricing, render, risk


def new_quote_number(prefix: str) -> str:
    return f"{prefix}-Q-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2).upper()}"


def assemble_quote_draft(
    raw_email: str,
    usage: llm.UsageTracker | None = None,
    on_stage=None,
    profile: CompanyProfile | None = None,
) -> tuple[QuoteDraft, "Inquiry"]:
    """Run stages intake → fx → pricing → risk → drafting; return (draft, inquiry).

    `profile` is the seller's CompanyProfile (per-user). Defaults to load_profile().
    """

    def note(stage: str) -> None:
        if on_stage:
            on_stage(stage)

    if profile is None:
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


CENT = Decimal("0.01")


def reprice_quote(quote: QuoteDraft, edits: dict) -> QuoteDraft:
    """Rebuild a QuoteDraft from human line-item edits. All money is Decimal —
    the human sets qty / unit price / discount %, the server recomputes totals.

    `edits` shape (any key optional):
      {
        "customer": {"contact_name","company","email"},
        "cover": {"cover_letter_en","cover_letter_zh","answers_en","answers_zh"},
        "lines": [ {"sku","name_en","name_zh","unit","unit_zh",
                    "quantity","unit_price_usd","discount_pct","note"} , ... ],
        "extra_notes_en": [str], "extra_notes_zh": [str],
      }
    Lines are fully replaced by the provided list (add = include a new entry,
    remove = omit it). Missing/invalid numbers are clamped, never crash.
    Legal terms, seller, FX, and risk flags are preserved from the original;
    the deterministic rule flags are NOT re-run here (kept as-is) so the
    human's edit is exactly what they see.
    """
    from decimal import ROUND_HALF_UP, InvalidOperation

    def dec(v, default="0") -> Decimal:
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError, TypeError):
            d = Decimal(default)
        return d if d.is_finite() else Decimal(default)

    fx = quote.fx
    new_lines: list[PricedLine] = []
    for raw in edits.get("lines", [l.model_dump() for l in quote.lines]):
        qty = dec(raw.get("quantity"), "0")
        if qty <= 0:
            continue  # a zeroed-out line is a removal
        unit_price = dec(raw.get("unit_price_usd"), "0")
        if unit_price < 0:
            unit_price = Decimal("0")
        pct = dec(raw.get("discount_pct"), "0")
        pct = min(max(pct, Decimal("0")), Decimal("100"))
        gross = (unit_price * qty).quantize(CENT, ROUND_HALF_UP)
        net = (gross * (Decimal("100") - pct) / Decimal("100")).quantize(CENT, ROUND_HALF_UP)
        new_lines.append(
            PricedLine(
                sku=str(raw.get("sku") or "CUSTOM"),
                name_en=str(raw.get("name_en") or raw.get("name") or "Item"),
                name_zh=str(raw.get("name_zh") or raw.get("name_en") or "项目"),
                unit=str(raw.get("unit") or "unit"),
                unit_zh=str(raw.get("unit_zh") or "件"),
                quantity=qty,
                unit_price_usd=unit_price,
                discount_pct=pct,
                line_total_usd=net,
                line_total_cny=(net * fx.rate).quantize(CENT, ROUND_HALF_UP),
                note=(raw.get("note") or (f"Discount {pct}% applied" if pct else None)),
            )
        )

    subtotal = sum((l.unit_price_usd * l.quantity for l in new_lines), Decimal("0")).quantize(CENT, ROUND_HALF_UP)
    total = sum((l.line_total_usd for l in new_lines), Decimal("0")).quantize(CENT, ROUND_HALF_UP)
    discount = (subtotal - total).quantize(CENT, ROUND_HALF_UP)
    total_cny = (total * fx.rate).quantize(CENT, ROUND_HALF_UP)

    data = quote.model_dump()
    data.update(
        lines=[l.model_dump() for l in new_lines],
        subtotal_usd=subtotal,
        discount_usd=discount,
        total_usd=total,
        total_cny=total_cny,
    )
    if "customer" in edits and isinstance(edits["customer"], dict):
        data["customer"] = {**data["customer"], **{k: v for k, v in edits["customer"].items() if v is not None}}
    if "cover" in edits and isinstance(edits["cover"], dict):
        data["cover"] = {**data["cover"], **{k: v for k, v in edits["cover"].items() if v is not None}}
    for key in ("extra_notes_en", "extra_notes_zh"):
        if isinstance(edits.get(key), list):
            data[key] = [str(x) for x in edits[key]]
    return QuoteDraft.model_validate(data)


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
