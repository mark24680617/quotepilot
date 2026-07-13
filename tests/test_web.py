import threading
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from quotepilot.models import CoverLetters, Customer, FxRate, QuoteDraft, RiskFlag
from quotepilot.profile import load_profile
from quotepilot.web.app import WebGate, app

from conftest import ADMIN_TEST_PASSWORD

client = TestClient(app)


def auth_headers(username="tester", password="testpass123"):
    r = client.post("/api/auth", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


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
    h = auth_headers()
    assert client.get("/artifacts/../x/quote.html", headers=h).status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/../../.env", headers=h).status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/x.py", headers=h).status_code == 404
    # unauthenticated -> 401
    assert client.get("/artifacts/20260101-000000-aa/x.html").status_code == 401


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
    assert client.get("/api/bootstrap").status_code == 401  # auth required
    resp = client.get("/api/bootstrap", headers=auth_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"] == "tester"
    assert "inquiry_zh_1.txt" in data["samples"]


def test_api_submit_validation():
    resp = client.post("/api/submit", json={"email_text": "hi"}, headers=auth_headers())
    assert resp.status_code == 422


def test_api_unknown_submission():
    h = auth_headers()
    assert client.get("/api/s/nope", headers=h).status_code == 404
    assert client.post("/api/s/nope/decision", json={"action": "approve"}, headers=h).status_code == 404


def test_auth_login_and_signup():
    # new username auto-creates
    r1 = client.post("/api/auth", json={"username": "newuser1", "password": "hunter2x"})
    assert r1.status_code == 200 and r1.json()["username"] == "newuser1"
    # same username, wrong (but valid-length) password -> 401
    assert client.post("/api/auth", json={"username": "newuser1", "password": "WRONGPASS"}).status_code == 401
    # correct password -> 200
    assert client.post("/api/auth", json={"username": "newuser1", "password": "hunter2x"}).status_code == 200
    # short password -> 422
    assert client.post("/api/auth", json={"username": "u2", "password": "x"}).status_code == 422
    # admin default password works
    assert client.post("/api/auth", json={"username": "admin", "password": ADMIN_TEST_PASSWORD}).status_code == 200


def test_judge_demo_account_gets_full_profile():
    # public judge account: seeded automatically, password is public by design
    r = client.post("/api/auth", json={"username": "judge", "password": "qwen2026"})
    assert r.status_code == 200
    h = {"Authorization": "Bearer " + r.json()["token"]}
    prof = client.get("/api/profile", headers=h).json()
    assert prof["seller"]["name_en"]        # LUQ LABS demo profile, not blank
    assert prof["catalog"]
    # wrong password on the seeded account -> 401 (it's a real account)
    assert client.post("/api/auth", json={"username": "judge", "password": "WRONGPASS"}).status_code == 401


def test_new_user_gets_blank_profile_admin_gets_luqlabs():
    admin_h = {"Authorization": "Bearer " + client.post(
        "/api/auth", json={"username": "admin", "password": ADMIN_TEST_PASSWORD}).json()["token"]}
    admin_prof = client.get("/api/profile", headers=admin_h).json()
    assert admin_prof["seller"]["name_en"]  # LUQ LABS, non-empty
    assert admin_prof["catalog"]

    new_h = auth_headers("blankco", "blankpass1")
    blank = client.get("/api/profile", headers=new_h).json()
    assert blank["seller"]["name_en"] == ""     # blank identity
    assert blank["catalog"] == []               # empty catalog


def test_run_ownership_isolation():
    from datetime import datetime, timezone
    from quotepilot.web import app as appmod

    gate = WebGate(on_review=lambda: None)
    gate.quote = make_quote()
    sub = appmod.Submission(
        sid="own-sid", source="test", created_at=datetime.now(timezone.utc),
        status="awaiting_approval", stages=[], gate=gate, owner_user="alice",
    )
    with appmod.SUBMISSIONS_LOCK:
        appmod.SUBMISSIONS["own-sid"] = sub
    try:
        bob = auth_headers("bobuser", "bobpass123")
        # unauthenticated -> 401
        assert client.post("/api/s/own-sid/decision", json={"action": "reject"}).status_code == 401
        # different user -> 403
        assert client.post("/api/s/own-sid/decision", json={"action": "reject"}, headers=bob).status_code == 403
        assert client.get("/api/s/own-sid", headers=bob).status_code == 403
        # owner -> allowed
        alice = auth_headers("alice", "alicepass1")
        assert client.post("/api/s/own-sid/decision", json={"action": "reject"}, headers=alice).status_code == 200
    finally:
        with appmod.SUBMISSIONS_LOCK:
            appmod.SUBMISSIONS.pop("own-sid", None)


def test_artifact_ownership_gate(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from quotepilot.models import Decision, RunResult
    from quotepilot.web import app as appmod

    runs = tmp_path / "runs"
    run_dir = runs / "20260101-000000-ab"
    run_dir.mkdir(parents=True)
    (run_dir / "quote.html").write_text("<h1>secret quote</h1>")
    monkeypatch.setattr(appmod, "RUNS_DIR", runs)

    result = RunResult(
        run_id="20260101-000000-ab",
        decision=Decision(action="approve", notes=None, decided_at=datetime.now(timezone.utc)),
        quote=make_quote(),
        artifacts={"quote_html": str(run_dir / "quote.html")},
    )
    sub = appmod.Submission(
        sid="art-sid", source="test", created_at=datetime.now(timezone.utc),
        status="approved", stages=[], gate=WebGate(on_review=lambda: None),
        owner_user="alice", result=result,
    )
    with appmod.SUBMISSIONS_LOCK:
        appmod.SUBMISSIONS["art-sid"] = sub
    try:
        url = "/artifacts/20260101-000000-ab/quote.html"
        assert client.get(url).status_code == 401                               # unauth
        assert client.get(url, headers=auth_headers("mallory", "mallory1")).status_code == 404  # not owner
        assert client.get(url, headers=auth_headers("alice", "alicepass1")).status_code == 200   # owner
        admin_h = {"Authorization": "Bearer " + client.post(
            "/api/auth", json={"username": "admin", "password": ADMIN_TEST_PASSWORD}).json()["token"]}
        assert client.get(url, headers=admin_h).status_code == 200               # admin
    finally:
        with appmod.SUBMISSIONS_LOCK:
            appmod.SUBMISSIONS.pop("art-sid", None)


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
    h = auth_headers()
    assert client.post("/api/submit", json={"email_text": "hi"}, headers=h).status_code == 422
    huge = "A" * 25_000
    assert client.post("/api/submit", json={"email_text": huge}, headers=h).status_code == 422
    # unauthenticated submit -> 401
    assert client.post("/api/submit", json={"email_text": "x" * 50}).status_code == 401


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
