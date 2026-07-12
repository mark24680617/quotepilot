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


def test_get_profile():
    client = TestClient(app)
    response = client.get("/api/profile")
    assert response.status_code == 200
    
    data = response.json()
    assert "seller" in data
    assert isinstance(data["seller"]["name_en"], str)
    assert len(data["seller"]["name_en"]) > 0
    assert "catalog" in data
    assert isinstance(data["catalog"], list)


def test_put_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("QP_PROFILE_STORE", str(tmp_path / "p.json"))
    
    client = TestClient(app)
    
    # Get current profile
    response = client.get("/api/profile")
    assert response.status_code == 200
    current_data = response.json()
    
    # Modify the name
    current_data["seller"]["name_en"] = "Acme Ltd"
    
    # PUT the modified profile
    response = client.put("/api/profile", json=current_data)
    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is True
    assert "saved_to" in result
    
    # GET again to verify the change
    response = client.get("/api/profile")
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["seller"]["name_en"] == "Acme Ltd"


def test_put_invalid():
    client = TestClient(app)
    
    # Try to PUT with invalid data
    response = client.put("/api/profile", json={"seller": {}})
    assert response.status_code == 422


def test_import_with_invalid_scheme():
    client = TestClient(app)
    
    # Try to import with ftp URL
    response = client.post("/api/profile/import", json={"url": "ftp://x"})
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
