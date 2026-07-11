import ipaddress
import re
import socket
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from quotepilot.config import CODER_MODEL
from quotepilot.llm import structured
from quotepilot.models import CatalogItem
from quotepilot.profile import CompanyProfile, load_profile, save_profile


_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}


def _ip_blocked(ip_str: str) -> bool:
    if ip_str in _METADATA_IPS:
        return True
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved


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
def get_profile():
    profile = load_profile()
    return profile.model_dump(mode="json")


@router.put("/api/profile")
def update_profile(profile: CompanyProfile):
    path = save_profile(profile)
    return {"ok": True, "saved_to": str(path)}


@router.post("/api/profile/import")
def import_profile(request: ImportRequest):
    # Step 1: Validate URL and fetch content
    parsed = urlparse(request.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="URL must use http or https scheme")

    try:
        response = _fetch_guarded(request.url)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {str(e)}")

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
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {e}")

    # Step 4: Build response draft
    current = load_profile()

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
