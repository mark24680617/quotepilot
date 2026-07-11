from datetime import date
from decimal import Decimal

from quotepilot.models import (
    CoverLetters,
    Customer,
    FxRate,
    PricedLine,
    QuoteDraft,
    RiskFlag,
)
from quotepilot.profile import load_profile
from quotepilot.stages import render

PROFILE = load_profile()


def make_quote():
    fx = FxRate(rate=Decimal("7.20"), source="test", as_of="2026-07-09T00:00:00Z")
    line = PricedLine(
        sku="CR-ENT",
        name_en="CitizenReady AI — Enterprise License",
        name_zh="CitizenReady AI 企业版许可",
        unit="seat/year",
        unit_zh="席位/年",
        quantity=Decimal("80"),
        unit_price_usd=Decimal("290.00"),
        discount_pct=Decimal("8"),
        line_total_usd=Decimal("21344.00"),
        line_total_cny=Decimal("153676.80"),
    )
    return QuoteDraft(
        quote_number="LUQ-Q-20260709-TEST",
        seller=PROFILE.seller,
        issue_date=date(2026, 7, 9),
        valid_until=date(2026, 8, 8),
        customer=Customer(contact_name="Wei Zhang", company="HZ Precision", email="w@x.cn"),
        lines=[line],
        subtotal_usd=Decimal("23200.00"),
        discount_usd=Decimal("1856.00"),
        total_usd=Decimal("21344.00"),
        total_cny=Decimal("153676.80"),
        fx=fx,
        cover=CoverLetters(
            cover_letter_en="Thank you for your inquiry.",
            cover_letter_zh="感谢您的询价。",
            answers_en="Yes, wire transfer is available.",
            answers_zh="可以,支持电汇付款。",
        ),
        payment_terms_en=PROFILE.terms.payment_en,
        payment_terms_zh=PROFILE.terms.payment_zh,
        legal_en=PROFILE.terms.legal_en,
        legal_zh=PROFILE.terms.legal_zh,
        risk_flags=[
            RiskFlag(code="X", severity="info", message_en="note", message_zh="备注")
        ],
    )


def test_quote_html_renders_bilingual():
    html = render.render_quote_html(make_quote())
    assert "LUQ-Q-20260709-TEST" in html
    assert "CitizenReady AI 企业版许可" in html
    assert "21,344.00" in html
    assert "153,676.80" in html
    assert "HKIAC" in html and "香港国际仲裁中心" in html
    assert "中文文本为唯一正式文本" in html


def test_reply_email_bilingual():
    email = render.render_reply_email(make_quote())
    assert "感谢您的询价" in email
    assert "Thank you for your inquiry." in email
    assert "LUQ-Q-20260709-TEST" in email
