"""Render stage: quote HTML document + bilingual reply email draft."""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config
from ..models import QuoteDraft

_env = Environment(
    loader=FileSystemLoader(config.TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def render_quote_html(quote: QuoteDraft) -> str:
    template = _env.get_template("quote.html.j2")
    return template.render(q=quote, seller=quote.seller)


def render_reply_email(quote: QuoteDraft) -> str:
    """Bilingual reply email draft in Markdown (body only)."""
    c = quote.cover
    parts = [
        f"Subject / 主题: Quotation {quote.quote_number} — {quote.seller.name_en}",
        "",
        "----- 中文 -----",
        "",
        c.cover_letter_zh.strip(),
    ]
    if c.answers_zh.strip():
        parts += ["", "**您的问题答复:**", c.answers_zh.strip()]
    parts += [
        "",
        f"报价单编号:{quote.quote_number}(有效期至 {quote.valid_until.isoformat()},见附件)",
        f"含税前合计:USD {quote.total_usd:,}(约 CNY {quote.total_cny:,},"
        f"汇率 {quote.fx.rate} {'[参考价]' if quote.fx.offline else ''})",
        "",
        "----- English -----",
        "",
        c.cover_letter_en.strip(),
    ]
    if c.answers_en.strip():
        parts += ["", "**Answers to your questions:**", c.answers_en.strip()]
    parts += [
        "",
        f"Quote {quote.quote_number}, valid until {quote.valid_until.isoformat()} (attached).",
        f"Total: USD {quote.total_usd:,} (≈ CNY {quote.total_cny:,} at {quote.fx.rate}"
        f"{', indicative' if quote.fx.offline else ''}).",
        "",
        f"{quote.seller.name_en} · {quote.seller.website} · {quote.seller.email}",
    ]
    return "\n".join(parts)
