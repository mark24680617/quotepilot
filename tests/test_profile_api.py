from decimal import Decimal
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
