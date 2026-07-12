import ipaddress
import json
import logging
import re
import socket
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from quotepilot.config import CODER_MODEL
from quotepilot.llm import structured
from quotepilot.models import CatalogItem
from quotepilot.profile import CompanyProfile, load_profile, save_profile
from quotepilot.web import auth, guard

logger = logging.getLogger("quotepilot.web")

_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}


def _ip_blocked(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    # IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) must be checked as its v4.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if str(ip) in _METADATA_IPS:
        return True
    # Only allow globally-routable unicast — this rejects private, loopback,
    # link-local (incl. cloud metadata 169.254/100.100.100.200), reserved,
    # multicast, and unspecified addresses in one check.
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _blocked_host(hostname: str) -> bool:
    """SSRF guard: refuse localhost/metadata names, and any host whose DNS
    resolution includes a private/loopback/link-local/reserved/metadata IP.
    (Residual DNS-rebinding TOCTOU is accepted for this demo.)"""
    hostname = (hostname or "").rstrip(".").lower()
    if not hostname or hostname in ("localhost", "metadata"):
        return True
    try:
        ipaddress.ip_address(hostname)
        return _ip_blocked(hostname)  # literal IP
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return True  # unresolvable -> refuse
    return any(_ip_blocked(info[4][0]) for info in infos)


def _fetch_guarded(url: str, max_hops: int = 3) -> httpx.Response:
    """GET with redirects followed manually so every hop is re-validated."""
    for _ in range(max_hops + 1):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or _blocked_host(parsed.hostname or ""):
            raise HTTPException(status_code=422, detail="URL host not allowed")
        response = httpx.get(url, timeout=15, follow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise HTTPException(status_code=502, detail="Redirect without location")
            url = str(httpx.URL(url).join(location))
            continue
        response.raise_for_status()
        return response
    raise HTTPException(status_code=502, detail="Too many redirects")


def _parse_price(raw: Optional[str]) -> Optional[Decimal]:
    if not raw:
        return None
    cleaned = re.sub(r"[^0-9.]", "", raw)
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None

router = APIRouter()


class _ImportedItem(BaseModel):
    sku: str  # generate a SHORT-UPPERCASE sku if not evident
    name_en: str
    name_zh: str  # translate if the site is monolingual
    description_en: str = ""
    description_zh: str = ""
    unit: str = "unit"
    unit_zh: str = "件"
    unit_price_usd: Optional[str] = None  # string decimal if a price is visible, else null


class _ImportedProfile(BaseModel):
    name_en: str
    name_zh: str
    website: str = ""
    email: str = ""
    description: str = ""
    products: List[_ImportedItem] = []


class ImportRequest(BaseModel):
    url: str

    @field_validator("url")
    def validate_url(cls, v):
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL must use http or https scheme")
        return v


@router.get("/api/profile")
def get_profile(request: Request):
    user = auth.current_user(request)
    return load_profile(user).model_dump(mode="json")


@router.put("/api/profile")
def update_profile(profile: CompanyProfile, request: Request):
    user = auth.current_user(request)
    guard.rate_limit(request, "profile_write")
    if len(profile.catalog) > guard.MAX_LINE_ITEMS:
        raise HTTPException(status_code=422, detail=f"Catalog too large (max {guard.MAX_LINE_ITEMS} items)")
    path = save_profile(profile, user)
    return {"ok": True, "saved_to": str(path)}


class _Translation(BaseModel):
    index: int
    text: str


class _Translations(BaseModel):
    items: List[_Translation]


# Bilingual field pairs to auto-complete. Legal terms (legal_en/legal_zh) are
# DELIBERATELY excluded — legal clauses are never AI-written/translated.
def _complete_profile(profile: CompanyProfile) -> tuple[CompanyProfile, list[str]]:
    from quotepilot.config import PLANNER_MODEL

    data = profile.model_dump()
    slots: list[tuple[str, str, object, str]] = []  # (source_text, target_label, container, key_to_set)

    def pair(container: dict, en_key: str, zh_key: str) -> None:
        en = (container.get(en_key) or "").strip()
        zh = (container.get(zh_key) or "").strip()
        if en and not zh:
            slots.append((en, "Simplified Chinese", container, zh_key))
        elif zh and not en:
            slots.append((zh, "English", container, en_key))

    s = data["seller"]
    pair(s, "name_en", "name_zh")
    pair(s, "jurisdiction_en", "jurisdiction_zh")
    tm = data["terms"]
    pair(tm, "payment_en", "payment_zh")
    pair(tm, "tax_note_en", "tax_note_zh")  # legal_en/legal_zh intentionally NOT translated
    for item in data["catalog"]:
        pair(item, "name_en", "name_zh")
        pair(item, "description_en", "description_zh")
        pair(item, "unit", "unit_zh")

    if not slots:
        return profile, []

    guard.daily_gate("import")  # this calls a paid model — count against the daily cap
    payload = [{"index": i, "target_language": tgt, "text": txt} for i, (txt, tgt, _, _) in enumerate(slots)]
    result: _Translations = structured(
        model=PLANNER_MODEL,
        system=(
            "You translate short business fields (company identity, payment/tax notes, "
            "product names, descriptions, units) between English and Simplified Chinese. "
            "For each item, translate its text into the given target_language, producing "
            "natural business wording (商务风格, not literal). Return one translation per "
            "index. Output translations only — no notes, no quotes."
        ),
        user="Translate each item to its target_language:\n" + json.dumps(payload, ensure_ascii=False),
        schema=_Translations,
        max_tokens=2000,
    )
    by_index = {t.index: (t.text or "").strip() for t in result.items}
    filled: list[str] = []
    for i, (_txt, _tgt, container, key) in enumerate(slots):
        tr = by_index.get(i)
        if tr:
            container[key] = tr
            filled.append(key)
    return CompanyProfile.model_validate(data), filled


@router.post("/api/profile/save")
def save_profile_completed(profile: CompanyProfile, request: Request):
    """Auto-fill missing-language fields (except legal terms) with Qwen, then save.

    This is the Settings 'Save' path: fill EN/中文 gaps a human left, so a
    one-language entry becomes a complete bilingual profile.
    """
    user = auth.current_user(request)
    guard.rate_limit(request, "profile_write")
    if len(profile.catalog) > guard.MAX_LINE_ITEMS:
        raise HTTPException(status_code=422, detail=f"Catalog too large (max {guard.MAX_LINE_ITEMS} items)")
    try:
        completed, filled = _complete_profile(profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("profile auto-complete failed: %s", e)
        completed, filled = profile, []  # translation failed -> save what the user entered
    path = save_profile(completed, user)
    return {
        "ok": True,
        "profile": completed.model_dump(mode="json"),
        "filled": filled,
        "saved_to": str(path),
    }


@router.post("/api/profile/import")
def import_profile(body: ImportRequest, request: Request):
    user = auth.current_user(request)
    guard.rate_limit(request, "import")
    guard.daily_gate("import")  # website-import calls a paid model — cap it

    # Step 1: Validate URL and fetch content
    parsed = urlparse(body.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="URL must use http or https scheme")

    try:
        response = _fetch_guarded(body.url)
    except httpx.HTTPError as e:
        logger.warning("import fetch failed for %s: %s", parsed.hostname, e)
        raise HTTPException(status_code=502, detail="Failed to fetch URL")

    # Truncate body to 400_000 chars
    content = response.text[:400_000]

    # Step 2: Strip to visible text
    # Remove script and style blocks
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    # Remove all HTML tags
    content = re.sub(r'<[^>]+>', '', content)
    # Collapse whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    # Truncate to 12_000 chars
    content = content[:12_000]

    # Step 3: LLM extraction
    try:
        extracted: _ImportedProfile = structured(
            model=CODER_MODEL,
            system=(
                "Extract the company identity and product/service list from the page text. "
                "Translate names/descriptions to produce BOTH English and Simplified Chinese. "
                "Invent nothing that is not on the page. Unknown prices stay null."
            ),
            user=content,
            schema=_ImportedProfile,
            max_tokens=3000,
        )
    except Exception as e:
        logger.warning("import extraction failed: %s", e)
        raise HTTPException(status_code=502, detail="AI extraction failed")

    # Step 4: Build response draft on top of the user's current profile
    current = load_profile(user)

    # Update seller info from extraction, keeping current values where extraction is empty
    seller_info = current.seller.model_copy()
    if extracted.name_en:
        seller_info.name_en = extracted.name_en
    if extracted.name_zh:
        seller_info.name_zh = extracted.name_zh
    if extracted.website:
        seller_info.website = extracted.website
    if extracted.email:
        seller_info.email = extracted.email
    if extracted.description:
        seller_info.description = extracted.description

    # Build catalog items
    catalog_items = []
    needs_price = []
    for item in extracted.products:
        price = _parse_price(item.unit_price_usd)
        if price is None:
            price = Decimal("0.00")
            needs_price.append(item.name_en)

        catalog_item = CatalogItem(
            sku=item.sku,
            name_en=item.name_en,
            name_zh=item.name_zh,
            description_en=item.description_en,
            description_zh=item.description_zh,
            unit=item.unit,
            unit_zh=item.unit_zh,
            unit_price_usd=price,
            volume_discounts=[]
        )
        catalog_items.append(catalog_item)

    # Create new profile with updated seller and catalog, but keep existing terms and rules
    new_profile = CompanyProfile(
        seller=seller_info,
        terms=current.terms,
        rules=current.rules,
        catalog=catalog_items
    )

    return {
        "draft": new_profile.model_dump(mode="json"),
        "needs_price": needs_price,
        "note": "Review and save; legal terms were kept from the current profile."
    }
