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


def _store_path() -> Path:
    """Writable store location: env override (e.g. /tmp/profile.json on FC),
    else a gitignored local file — the bundled default is never overwritten."""
    raw = os.getenv("QP_PROFILE_STORE")
    return Path(raw) if raw else config.DATA_DIR / "company_profile.local.json"


def load_profile() -> CompanyProfile:
    store = _store_path()
    if store.exists():
        try:
            return CompanyProfile.model_validate_json(store.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupt store falls back to the bundled default
    return CompanyProfile.model_validate_json(
        DEFAULT_PROFILE_PATH.read_text(encoding="utf-8")
    )


def save_profile(profile: CompanyProfile) -> Path:
    """Persist atomically to the writable store (never the bundled default)."""
    dest = _store_path()
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
