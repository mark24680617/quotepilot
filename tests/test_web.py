import threading
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from quotepilot import config
from quotepilot.models import CoverLetters, Customer, FxRate, QuoteDraft, RiskFlag
from quotepilot.web.app import WebGate, app

client = TestClient(app)


def make_quote(severity="info"):
    return QuoteDraft(
        quote_number="LUQ-Q-TEST-0001",
        issue_date=date(2026, 7, 9),
        valid_until=date(2026, 8, 8),
        customer=Customer(contact_name="T", company="TestCo", email="t@x.cn"),
        lines=[],
        subtotal_usd=Decimal("0"),
        discount_usd=Decimal("0"),
        total_usd=Decimal("0"),
        total_cny=Decimal("0"),
        fx=FxRate(rate=Decimal("7.2"), source="test", as_of="2026-07-09"),
        cover=CoverLetters(
            cover_letter_en="e", cover_letter_zh="z", answers_en="", answers_zh=""
        ),
        payment_terms_en="p",
        payment_terms_zh="p",
        legal_en="l",
        legal_zh="l",
        risk_flags=[
            RiskFlag(code="T", severity=severity, message_en="m", message_zh="m")
        ],
    )


def test_dashboard_renders():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "QuotePilot" in resp.text


def test_sample_endpoint():
    resp = client.get("/sample/inquiry_zh_1.txt")
    assert resp.status_code == 200
    assert "RentalNote" in resp.json()["text"]


def test_sample_rejects_bad_names():
    assert client.get("/sample/../secrets.txt").status_code in (404, 422)
    assert client.get("/sample/evil.py").status_code == 404


def test_artifacts_rejects_traversal():
    assert client.get("/artifacts/../x/quote.html").status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/../../.env").status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/x.py").status_code == 404


def test_unknown_submission_404():
    assert client.get("/s/nope").status_code == 404
    assert client.post("/s/nope/decision", data={"action": "approve"}).status_code == 404


def test_webgate_approve_roundtrip():
    reviewed = threading.Event()
    gate = WebGate(on_review=reviewed.set)
    out = {}

    def worker():
        out["decision"] = gate.review(make_quote())

    t = threading.Thread(target=worker)
    t.start()
    assert reviewed.wait(5)
    assert gate.resolve("approve", "ok") is True
    t.join(5)
    assert out["decision"].action == "approve"
    assert out["decision"].notes == "ok"
    # second resolve is a no-op
    assert gate.resolve("reject", None) is False


def test_api_bootstrap():
    resp = client.get("/api/bootstrap")
    assert resp.status_code == 200
    data = resp.json()
    assert "samples" in data
    assert "submissions" in data
    assert "archived" in data
    assert "inquiry_zh_1.txt" in data["samples"]


def test_api_submit_validation():
    resp = client.post("/api/submit", json={"email_text": "hi"})
    assert resp.status_code == 422


def test_api_unknown_submission():
    resp = client.get("/api/s/nope")
    assert resp.status_code == 404
    
    resp = client.post("/api/s/nope/decision", json={"action": "approve"})
    assert resp.status_code == 404


def test_cors():
    resp = client.get("/", headers={"Origin": "https://example.github.io"})
    assert resp.headers.get("access-control-allow-origin") == "*"
