from decimal import Decimal

from quotepilot.models import FxRate, Inquiry, LineRequest
from quotepilot.profile import load_profile
from quotepilot.stages import pricing

FX = FxRate(rate=Decimal("7.20"), source="test", as_of="2026-07-09T00:00:00Z")
PROFILE = load_profile()


def make_inquiry(requests):
    return Inquiry(language="en", requests=requests, summary="test")


def test_catalog_loads():
    skus = {c.sku for c in PROFILE.catalog}
    assert {"CR-ENT", "RN-SAAS", "SVC-DEV"} <= skus


def test_deterministic_match_and_volume_discount():
    inquiry = make_inquiry(
        [LineRequest(product_name="CitizenReady AI", quantity=Decimal("80"))]
    )
    lines, unmatched = pricing.price_inquiry(inquiry, FX, PROFILE)
    assert not unmatched
    assert len(lines) == 1
    line = lines[0]
    assert line.sku == "CR-ENT"
    # 80 seats → 8% tier: 80 * 290 = 23200; net = 23200 * 0.92 = 21344.00
    assert line.discount_pct == Decimal("8")
    assert line.line_total_usd == Decimal("21344.00")
    assert line.line_total_cny == Decimal("21344.00") * Decimal("7.20")


def test_missing_quantity_goes_unmatched():
    inquiry = make_inquiry([LineRequest(product_name="RentalNote", quantity=None)])
    lines, unmatched = pricing.price_inquiry(inquiry, FX, PROFILE)
    assert not lines
    assert len(unmatched) == 1
    assert "Quantity" in unmatched[0].reason


def test_totals():
    inquiry = make_inquiry(
        [
            LineRequest(product_name="CR-ENT", quantity=Decimal("80")),
            LineRequest(product_name="CR-ONB", quantity=Decimal("1")),
        ]
    )
    lines, _ = pricing.price_inquiry(inquiry, FX, PROFILE)
    subtotal, discount, total, total_cny = pricing.totals(lines, FX)
    assert subtotal == Decimal("28000.00")  # 23200 + 4800
    assert discount == Decimal("1856.00")  # 8% of 23200
    assert total == Decimal("26144.00")
    assert total_cny == total * Decimal("7.20")
