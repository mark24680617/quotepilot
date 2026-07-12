from decimal import Decimal
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from quotepilot.profile import CompanyProfile, SellerInfo, TermsConfig, BusinessRules, CatalogItem
from quotepilot.web.app import app


class MockImportedProfile(BaseModel):
    name_en: str
    name_zh: str
    website: str = ""
    email: str = ""
    description: str = ""
    products: list = []


def _admin_headers(client):
    r = client.post("/api/auth", json={"username": "admin", "password": "88888888"})
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_get_profile():
    client = TestClient(app)
    assert client.get("/api/profile").status_code == 401  # auth required
    response = client.get("/api/profile", headers=_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["seller"]["name_en"], str)
    assert len(data["seller"]["name_en"]) > 0   # admin -> LUQ LABS
    assert isinstance(data["catalog"], list)


def test_put_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("QP_PROFILE_DIR", str(tmp_path / "profiles"))
    client = TestClient(app)
    hdr = _admin_headers(client)

    current_data = client.get("/api/profile", headers=hdr).json()
    current_data["seller"]["name_en"] = "Acme Ltd"
    response = client.put("/api/profile", json=current_data, headers=hdr)
    assert response.status_code == 200
    assert response.json()["ok"] is True

    updated = client.get("/api/profile", headers=hdr).json()
    assert updated["seller"]["name_en"] == "Acme Ltd"


def test_put_invalid():
    client = TestClient(app)
    # Invalid data with auth -> 422
    response = client.put("/api/profile", json={"seller": {}}, headers=_admin_headers(client))
    assert response.status_code == 422


def test_write_endpoints_require_auth():
    client = TestClient(app)
    valid = client.get("/api/profile", headers=_admin_headers(client)).json()
    # No auth -> 401 on every profile endpoint
    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json=valid).status_code == 401
    assert client.post("/api/profile/save", json=valid).status_code == 401
    assert client.post("/api/profile/import", json={"url": "https://example.com"}).status_code == 401
    # Bogus token -> 401
    assert client.put("/api/profile", json=valid, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_import_with_invalid_scheme():
    client = TestClient(app)
    # ftp URL, authenticated -> 422 (scheme rejected)
    response = client.post("/api/profile/import", json={"url": "ftp://x"},
                           headers=_admin_headers(client))
    assert response.status_code == 422


def test_ssrf_guard_blocks_internal_hosts():
    from quotepilot.web.profile_api import _blocked_host, _ip_blocked

    assert _ip_blocked("169.254.169.254") is True   # AWS/ECS metadata
    assert _ip_blocked("100.100.100.200") is True   # Alibaba metadata
    assert _ip_blocked("10.0.0.8") is True
    assert _ip_blocked("8.8.8.8") is False
    assert _blocked_host("localhost") is True
    assert _blocked_host("127.0.0.1") is True
    assert _blocked_host("LOCALHOST.") is True


def test_ssrf_guard_blocks_ipv6_mapped_and_shared():
    from quotepilot.web.profile_api import _ip_blocked

    # IPv4-mapped IPv6 to the AWS/ECS metadata IP must be blocked
    assert _ip_blocked("::ffff:169.254.169.254") is True
    # Alibaba metadata (100.64/10 shared address space)
    assert _ip_blocked("100.100.100.200") is True
    # 0.0.0.0 (unspecified) blocked; a public host allowed
    assert _ip_blocked("0.0.0.0") is True
    assert _ip_blocked("1.1.1.1") is False


def test_autocomplete_fills_gaps_but_not_legal(monkeypatch):
    from quotepilot.web import profile_api as pa
    from quotepilot.profile import CompanyProfile, load_profile

    base = load_profile().model_dump()
    base["seller"]["name_zh"] = ""
    base["catalog"][0]["name_zh"] = ""
    base["terms"]["legal_zh"] = ""       # must NOT be auto-translated
    prof = CompanyProfile.model_validate(base)

    class _I:
        def __init__(self, i, t): self.index, self.text = i, t

    class _T:
        def __init__(self, items): self.items = items

    def fake(**kw):
        payload = json.loads(kw["user"].split("target_language:\n", 1)[1])
        return _T([_I(p["index"], "ZH:" + p["text"][:6]) for p in payload])

    monkeypatch.setattr(pa, "structured", fake)
    monkeypatch.setattr(pa.guard, "daily_gate", lambda *a, **k: None)
    completed, filled = pa._complete_profile(prof)

    assert completed.seller.name_zh.startswith("ZH:")
    assert completed.catalog[0].name_zh.startswith("ZH:")
    assert completed.terms.legal_zh == ""      # legal untouched
    assert "legal_zh" not in filled


def test_autocomplete_noop_when_complete(monkeypatch):
    from quotepilot.web import profile_api as pa
    from quotepilot.profile import load_profile

    called = {"n": 0}
    monkeypatch.setattr(pa, "structured", lambda **k: (_ for _ in ()).throw(AssertionError("should not call model")))
    monkeypatch.setattr(pa.guard, "daily_gate", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    completed, filled = pa._complete_profile(load_profile())  # bundled profile is fully bilingual
    assert filled == []
    assert called["n"] == 0  # no model call, no daily-gate charge
