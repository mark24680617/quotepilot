from datetime import date
from decimal import Decimal

from quotepilot import core
from quotepilot.models import (
    CoverLetters,
    Customer,
    FxRate,
    PricedLine,
    QuoteDraft,
)
from quotepilot.profile import load_profile

PROFILE = load_profile()


def base_quote():
    fx = FxRate(rate=Decimal("7.00"), source="test", as_of="2026-07-11")
    line = PricedLine(
        sku="RN-SAAS", name_en="RentalNote", name_zh="RentalNote 物业",
        unit="property/year", unit_zh="物业/年",
        quantity=Decimal("100"), unit_price_usd=Decimal("59.00"),
        discount_pct=Decimal("10"), line_total_usd=Decimal("5310.00"),
        line_total_cny=Decimal("37170.00"),
    )
    return QuoteDraft(
        quote_number="LUQ-Q-TEST", seller=PROFILE.seller,
        issue_date=date(2026, 7, 11), valid_until=date(2026, 8, 10),
        customer=Customer(contact_name="Liu", company="AnJu", email="l@x.cn"),
        lines=[line],
        subtotal_usd=Decimal("5900.00"), discount_usd=Decimal("590.00"),
        total_usd=Decimal("5310.00"), total_cny=Decimal("37170.00"), fx=fx,
        cover=CoverLetters(cover_letter_en="e", cover_letter_zh="z", answers_en="", answers_zh=""),
        payment_terms_en="p", payment_terms_zh="p", legal_en="l", legal_zh="l",
    )


def test_edit_quantity_recomputes_totals():
    q = base_quote()
    edited = core.reprice_quote(q, {"lines": [{
        "sku": "RN-SAAS", "name_en": "RentalNote", "name_zh": "RentalNote 物业",
        "unit": "property/year", "unit_zh": "物业/年",
        "quantity": "200", "unit_price_usd": "59.00", "discount_pct": "10",
    }]})
    # 200 * 59 = 11800; net = 11800 * 0.9 = 10620.00
    assert edited.lines[0].line_total_usd == Decimal("10620.00")
    assert edited.total_usd == Decimal("10620.00")
    assert edited.subtotal_usd == Decimal("11800.00")
    assert edited.discount_usd == Decimal("1180.00")
    assert edited.total_cny == Decimal("10620.00") * Decimal("7.00")


def test_manual_price_and_discount_override():
    q = base_quote()
    edited = core.reprice_quote(q, {"lines": [{
        "sku": "RN-SAAS", "name_en": "RentalNote", "quantity": "100",
        "unit_price_usd": "50.00", "discount_pct": "20",
    }]})
    # 100*50=5000; net=5000*0.8=4000.00
    assert edited.lines[0].unit_price_usd == Decimal("50.00")
    assert edited.total_usd == Decimal("4000.00")


def test_add_and_remove_lines():
    q = base_quote()
    edited = core.reprice_quote(q, {"lines": [
        {"sku": "RN-SAAS", "name_en": "RentalNote", "quantity": "100",
         "unit_price_usd": "59.00", "discount_pct": "10"},
        {"sku": "CUSTOM", "name_en": "Onsite training", "name_zh": "现场培训",
         "quantity": "2", "unit_price_usd": "800.00", "discount_pct": "0"},
    ]})
    assert len(edited.lines) == 2
    # 5310 + 1600 = 6910
    assert edited.total_usd == Decimal("6910.00")
    # zero quantity removes a line
    removed = core.reprice_quote(q, {"lines": [
        {"sku": "RN-SAAS", "quantity": "0", "unit_price_usd": "59", "discount_pct": "10"},
    ]})
    assert removed.lines == []
    assert removed.total_usd == Decimal("0.00")


def test_bad_numbers_are_clamped_not_crash():
    q = base_quote()
    edited = core.reprice_quote(q, {"lines": [{
        "sku": "X", "name_en": "X", "quantity": "3",
        "unit_price_usd": "-5", "discount_pct": "250",
    }]})
    # unit price clamped to 0, discount clamped to 100 -> total 0
    assert edited.total_usd == Decimal("0.00")


def test_customer_and_cover_edits():
    q = base_quote()
    edited = core.reprice_quote(q, {
        "customer": {"company": "New Corp"},
        "cover": {"cover_letter_en": "Revised letter"},
    })
    assert edited.customer.company == "New Corp"
    assert edited.customer.contact_name == "Liu"  # preserved
    assert edited.cover.cover_letter_en == "Revised letter"
    # legal + seller preserved
    assert edited.legal_en == "l"
    assert edited.seller.name_en == PROFILE.seller.name_en
