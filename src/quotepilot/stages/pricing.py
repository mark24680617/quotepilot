"""Pricing stage: match requests to the catalog, apply discounts, convert FX.

Matching strategy: deterministic (SKU / name substring) first; anything left
over is mapped by qwen3-coder-plus against the catalog, then re-validated in
code. All arithmetic is Decimal — the LLM never does math.
"""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from pydantic import BaseModel, Field

from .. import config, llm
from ..models import (
    CatalogItem,
    FxRate,
    Inquiry,
    LineRequest,
    PricedLine,
    UnmatchedRequest,
    VolumeDiscount,
)

CENT = Decimal("0.01")


def load_catalog() -> list[CatalogItem]:
    data = json.loads(config.CATALOG_PATH.read_text(encoding="utf-8"))
    return [CatalogItem.model_validate(item) for item in data["items"]]


def _deterministic_match(req: LineRequest, catalog: list[CatalogItem]) -> Optional[CatalogItem]:
    name = req.product_name.strip().lower()
    for item in catalog:
        if name == item.sku.lower():
            return item
    for item in catalog:
        en = item.name_en.lower()
        if name in en or en.split(" — ")[0] in name:
            return item
        if item.name_zh and (name in item.name_zh or item.name_zh in req.product_name):
            return item
    return None


class _MappedRequest(BaseModel):
    product_name: str
    sku: Optional[str] = Field(
        default=None, description="Matching catalog SKU, or null if nothing fits"
    )
    confidence: str = Field(description="high / medium / low")


class _MappingResult(BaseModel):
    mappings: list[_MappedRequest]


def _llm_match(
    unresolved: list[LineRequest],
    catalog: list[CatalogItem],
    usage: llm.UsageTracker | None,
) -> dict[str, Optional[str]]:
    catalog_brief = [
        {"sku": c.sku, "name_en": c.name_en, "name_zh": c.name_zh, "unit": c.unit}
        for c in catalog
    ]
    result = llm.structured(
        config.CODER_MODEL,
        "You map customer product mentions to a product catalog. Only use SKUs "
        "that exist in the catalog. If no catalog item plausibly matches, sku=null. "
        "Do not guess across product families.",
        "Catalog:\n"
        + json.dumps(catalog_brief, ensure_ascii=False, indent=1)
        + "\n\nCustomer mentions:\n"
        + json.dumps([r.product_name for r in unresolved], ensure_ascii=False),
        _MappingResult,
        usage=usage,
        max_tokens=1000,
    )
    valid_skus = {c.sku for c in catalog}
    out: dict[str, Optional[str]] = {}
    for m in result.mappings:
        out[m.product_name] = m.sku if m.sku in valid_skus else None
    return out


def volume_discount_pct(item: CatalogItem, qty: Decimal) -> Decimal:
    pct = Decimal("0")
    for tier in sorted(item.volume_discounts, key=lambda t: t.min_qty):
        if qty >= tier.min_qty:
            pct = tier.pct
    return pct


def price_inquiry(
    inquiry: Inquiry,
    fx: FxRate,
    usage: llm.UsageTracker | None = None,
) -> tuple[list[PricedLine], list[UnmatchedRequest]]:
    catalog = load_catalog()
    lines: list[PricedLine] = []
    unmatched: list[UnmatchedRequest] = []

    resolved: dict[int, CatalogItem] = {}
    unresolved: list[tuple[int, LineRequest]] = []
    for i, req in enumerate(inquiry.requests):
        item = _deterministic_match(req, catalog)
        if item:
            resolved[i] = item
        else:
            unresolved.append((i, req))

    if unresolved:
        mapping = _llm_match([r for _, r in unresolved], catalog, usage)
        by_sku = {c.sku: c for c in catalog}
        for i, req in unresolved:
            sku = mapping.get(req.product_name)
            if sku:
                resolved[i] = by_sku[sku]

    for i, req in enumerate(inquiry.requests):
        item = resolved.get(i)
        if item is None:
            unmatched.append(
                UnmatchedRequest(
                    product_name=req.product_name,
                    reason="No matching product in catalog",
                )
            )
            continue
        if req.quantity is None or req.quantity <= 0:
            unmatched.append(
                UnmatchedRequest(
                    product_name=req.product_name,
                    reason="Quantity not stated — needs clarification",
                )
            )
            continue
        qty = req.quantity
        pct = volume_discount_pct(item, qty)
        gross = (item.unit_price_usd * qty).quantize(CENT, ROUND_HALF_UP)
        net = (gross * (Decimal("100") - pct) / Decimal("100")).quantize(CENT, ROUND_HALF_UP)
        lines.append(
            PricedLine(
                sku=item.sku,
                name_en=item.name_en,
                name_zh=item.name_zh,
                unit=item.unit,
                unit_zh=item.unit_zh,
                quantity=qty,
                unit_price_usd=item.unit_price_usd,
                discount_pct=pct,
                line_total_usd=net,
                line_total_cny=(net * fx.rate).quantize(CENT, ROUND_HALF_UP),
                note=(f"Volume discount {pct}% applied" if pct else None),
            )
        )
    return lines, unmatched


def totals(lines: list[PricedLine], fx: FxRate) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns (subtotal_usd_before_discount, discount_usd, total_usd, total_cny)."""
    subtotal = Decimal("0")
    total = Decimal("0")
    for line in lines:
        subtotal += (line.unit_price_usd * line.quantity).quantize(CENT, ROUND_HALF_UP)
        total += line.line_total_usd
    discount = (subtotal - total).quantize(CENT, ROUND_HALF_UP)
    total_cny = (total * fx.rate).quantize(CENT, ROUND_HALF_UP)
    return subtotal.quantize(CENT, ROUND_HALF_UP), discount, total.quantize(CENT, ROUND_HALF_UP), total_cny
