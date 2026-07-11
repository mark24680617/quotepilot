from decimal import Decimal

from quotepilot.models import FxRate, Inquiry, LineRequest, PricedLine, RequestedTerms
from quotepilot.profile import load_profile
from quotepilot.stages import risk

PROFILE = load_profile()


def make_inquiry(**kwargs):
    defaults = dict(language="en", requests=[], summary="test")
    defaults.update(kwargs)
    return Inquiry(**defaults)


def make_line(total="1000.00"):
    return PricedLine(
        sku="CR-ENT",
        name_en="x",
        name_zh="x",
        unit="seat/year",
        unit_zh="席位/年",
        quantity=Decimal("1"),
        unit_price_usd=Decimal(total),
        line_total_usd=Decimal(total),
        line_total_cny=Decimal(total) * Decimal("7.2"),
    )


def codes(flags):
    return {f.code for f in flags}


def test_block_when_nothing_priceable():
    flags = risk.rule_flags(make_inquiry(), [], [], Decimal("0"), "hello", PROFILE)
    assert "NO_PRICEABLE_LINES" in codes(flags)
    assert any(f.severity == "block" for f in flags)


def test_fapiao_detection_zh():
    flags = risk.rule_flags(
        make_inquiry(), [make_line()], [], Decimal("1000"), "请问能否开具增值税专用发票?", PROFILE
    )
    assert "FAPIAO_REQUEST" in codes(flags)


def test_wire_threshold():
    flags = risk.rule_flags(
        make_inquiry(), [make_line("60000.00")], [], Decimal("60000"), "big order", PROFILE
    )
    assert "WIRE_RECOMMENDED" in codes(flags)


def test_discount_above_floor():
    inquiry = make_inquiry(
        requested_terms=RequestedTerms(discount_request_pct=Decimal("20"))
    )
    flags = risk.rule_flags(inquiry, [make_line()], [], Decimal("1000"), "20% please", PROFILE)
    assert "DISCOUNT_ABOVE_FLOOR" in codes(flags)


def test_tight_deadline():
    inquiry = make_inquiry(requested_terms=RequestedTerms(deadline_days=5))
    flags = risk.rule_flags(inquiry, [make_line()], [], Decimal("1000"), "asap", PROFILE)
    assert "TIGHT_DEADLINE" in codes(flags)
