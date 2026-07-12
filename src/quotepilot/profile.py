"""Company profile: who is selling, on what terms, with what catalog.

QuotePilot is multi-company: everything seller-specific lives in a
CompanyProfile instead of code. The bundled default profile (LUQ LABS) is
the demo; deployments override it via the writable store (on Function
Compute that's /tmp — per-instance, which is fine for a demo).
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from . import config
from .models import CatalogItem, SellerInfo


class TermsConfig(BaseModel):
    payment_en: str
    payment_zh: str
    legal_en: str
    legal_zh: str
    tax_note_en: str = ""
    tax_note_zh: str = ""


class BusinessRules(BaseModel):
    quote_validity_days: int = 30
    wire_threshold_usd: Decimal = Decimal("50000")
    max_extra_discount_pct: Decimal = Decimal("15")
    urgent_deadline_days: int = 7
    quote_prefix: str = "QP"


class CompanyProfile(BaseModel):
    seller: SellerInfo
    terms: TermsConfig
    rules: BusinessRules = Field(default_factory=BusinessRules)
    catalog: list[CatalogItem] = Field(default_factory=list)


DEFAULT_PROFILE_PATH = config.DATA_DIR / "company_profile.json"
ADMIN_USER = "admin"  # the seeded account that owns the bundled LUQ LABS profile


def _profiles_dir() -> Path:
    raw = os.getenv("QP_PROFILE_DIR")
    return Path(raw) if raw else config.DATA_DIR / "profiles.local"


def _store_path(username: str | None = None) -> Path:
    """Per-user writable store; the single-store env override still works for
    back-compat (used by the CLI and tests)."""
    if username is None:
        raw = os.getenv("QP_PROFILE_STORE")
        return Path(raw) if raw else config.DATA_DIR / "company_profile.local.json"
    return _profiles_dir() / f"{username}.json"


def blank_profile() -> CompanyProfile:
    """An empty company profile — what every non-admin user starts with."""
    return CompanyProfile(
        seller=SellerInfo(name_en="", name_zh="", jurisdiction_en="", jurisdiction_zh="",
                          website="", email="", description=""),
        terms=TermsConfig(payment_en="", payment_zh="", legal_en="", legal_zh="",
                          tax_note_en="", tax_note_zh=""),
        rules=BusinessRules(),  # sensible numeric defaults
        catalog=[],
    )


def _bundled_default() -> CompanyProfile:
    return CompanyProfile.model_validate_json(DEFAULT_PROFILE_PATH.read_text(encoding="utf-8"))


def load_profile(username: str | None = None) -> CompanyProfile:
    store = _store_path(username)
    if store.exists():
        try:
            return CompanyProfile.model_validate_json(store.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupt store falls back below
    # No saved profile yet: admin (and the anonymous/CLI default) get LUQ LABS;
    # every other user starts blank.
    if username is None or username == ADMIN_USER:
        return _bundled_default()
    return blank_profile()


def save_profile(profile: CompanyProfile, username: str | None = None) -> Path:
    """Persist atomically to the (per-user) writable store; never the bundled default."""
    dest = _store_path(username)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(profile.model_dump_json(indent=2))
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
