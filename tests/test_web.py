import threading
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from quotepilot.models import CoverLetters, Customer, FxRate, QuoteDraft, RiskFlag
from quotepilot.profile import load_profile
from quotepilot.web.app import WebGate, app

client = TestClient(app)


def make_quote(severity="info"):
    return QuoteDraft(
        quote_number="LUQ-Q-TEST-0001",
        seller=load_profile().seller,
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


def test_cors_allows_pages_origin_only():
    ok = client.get("/", headers={"Origin": "https://mark24680617.github.io"})
    assert ok.headers.get("access-control-allow-origin") == "https://mark24680617.github.io"
    # a random origin is NOT reflected
    bad = client.get("/", headers={"Origin": "https://evil.example"})
    assert bad.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")
    # never combine with credentials
    assert ok.headers.get("access-control-allow-credentials") != "true"


def test_security_headers_present():
    r = client.get("/api/bootstrap")
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in r.headers.get("content-security-policy", "")


def test_submit_rejects_oversize_and_short():
    assert client.post("/api/submit", json={"email_text": "hi"}).status_code == 422
    huge = "A" * 25_000
    assert client.post("/api/submit", json={"email_text": huge}).status_code == 422


def test_owner_token_enforced_on_mutations():
    from datetime import datetime, timezone
    from quotepilot.web import app as appmod

    gate = WebGate(on_review=lambda: None)
    gate.quote = make_quote()
    sub = appmod.Submission(
        sid="unit-sid", source="test", created_at=datetime.now(timezone.utc),
        status="awaiting_approval", stages=[], gate=gate, owner_token="secret-tok",
    )
    with appmod.SUBMISSIONS_LOCK:
        appmod.SUBMISSIONS["unit-sid"] = sub
    try:
        # no token -> 403
        assert client.post("/api/s/unit-sid/decision", json={"action": "reject"}).status_code == 403
        # wrong token -> 403
        assert client.post("/api/s/unit-sid/decision", json={"action": "reject"},
                           headers={"X-QP-Owner-Token": "nope"}).status_code == 403
        # correct token -> processed (reject succeeds)
        ok = client.post("/api/s/unit-sid/decision", json={"action": "reject"},
                         headers={"X-QP-Owner-Token": "secret-tok"})
        assert ok.status_code == 200
    finally:
        with appmod.SUBMISSIONS_LOCK:
            appmod.SUBMISSIONS.pop("unit-sid", None)


def test_rate_limit_and_daily_gate():
    from quotepilot.web import guard

    class _Req:
        def __init__(self, ip):
            self.headers = {"x-forwarded-for": ip}
            self.client = None

    guard._ip_hits.clear()
    r = _Req("203.0.113.9")
    maxn = guard.LIMITS["submit"][0]
    for _ in range(maxn):
        guard.rate_limit(r, "submit")  # should not raise
    import pytest
    with pytest.raises(Exception):
        guard.rate_limit(r, "submit")  # over the limit -> 429
