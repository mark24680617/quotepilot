# Task T8: company-profile API + AI website import

QuotePilot is now multi-company: seller identity/terms/rules/catalog live in a
CompanyProfile. Expose it over the JSON API and add an AI-powered
"import from website" onboarding endpoint.

## Existing interfaces (import; do NOT redefine)

```python
# quotepilot.profile
class TermsConfig(BaseModel):   # payment_en/zh, legal_en/zh, tax_note_en/zh (strs)
class BusinessRules(BaseModel): # quote_validity_days:int, wire_threshold_usd:Decimal,
                                # max_extra_discount_pct:Decimal, urgent_deadline_days:int, quote_prefix:str
class CompanyProfile(BaseModel):
    seller: SellerInfo          # name_en,name_zh,jurisdiction_en,jurisdiction_zh,website,email,description
    terms: TermsConfig
    rules: BusinessRules
    catalog: list[CatalogItem]  # sku,name_en,name_zh,description_en,description_zh,unit,unit_zh,
                                # unit_price_usd:Decimal, volume_discounts:[{min_qty,pct}]
def load_profile() -> CompanyProfile
def save_profile(profile: CompanyProfile) -> Path

# quotepilot.llm
def structured(model, system, user, schema: Type[T], *, usage=None, temperature=0.2,
               max_tokens=2000, validation_retries=2) -> T
# quotepilot.config: WORKER_MODEL (qwen-flash), CODER_MODEL (qwen3-coder-plus)
```

## File to output: `src/quotepilot/web/profile_api.py`

A FastAPI APIRouter (`router = APIRouter()`) with:

### GET /api/profile
→ `load_profile().model_dump(mode="json")`

### PUT /api/profile
Body: full CompanyProfile JSON. Validate with `CompanyProfile.model_validate`
(422 on validation error — let FastAPI do it by typing the body param as
CompanyProfile). `save_profile(...)`; return `{"ok": True, "saved_to": str(path)}`.

### POST /api/profile/import
Body: `{"url": str}` (pydantic model). Flow:
1. Validate scheme is http/https (else 422). Fetch with httpx
   (`timeout=15`, `follow_redirects=True`); on fetch error return 502 with
   detail. Truncate body to 400_000 chars.
2. Strip to visible text: remove `<script>`/`<style>` blocks and all tags via
   regex, collapse whitespace, truncate to 12_000 chars.
3. LLM extraction (model=config.CODER_MODEL) into this schema (define with
   pydantic in the module):
   ```python
   class _ImportedItem(BaseModel):
       sku: str            # generate a SHORT-UPPERCASE sku if not evident
       name_en: str
       name_zh: str        # translate if the site is monolingual
       description_en: str = ""
       description_zh: str = ""
       unit: str = "unit"
       unit_zh: str = "件"
       unit_price_usd: str | None = None  # string decimal if a price is visible, else null
   class _ImportedProfile(BaseModel):
       name_en: str
       name_zh: str
       website: str = ""
       email: str = ""
       description: str = ""
       products: list[_ImportedItem] = []
   ```
   System prompt: extract the company identity and product/service list from
   the page text; translate names/descriptions to produce BOTH English and
   Simplified Chinese; invent nothing that is not on the page; unknown prices
   stay null.
4. Build the response draft: start from `current = load_profile()`, replace
   seller fields from the extraction (keep current values where extraction is
   empty), and build catalog items (price null → "0.00" and add the item name
   to a `needs_price` list). DO NOT touch terms/rules (legal text must never
   be LLM-generated) and DO NOT save — return
   `{"draft": <CompanyProfile dump>, "needs_price": [...], "note": "Review and save; legal terms were kept from the current profile."}`.

## File to output: `src/quotepilot/web/app.py` integration line

Do NOT re-emit app.py. Instead output a second file
`src/quotepilot/web/_wire_profile.txt` containing exactly the two lines to add
to app.py (import + `app.include_router(...)`) so the reviewer wires it in.

## File to output: `tests/test_profile_api.py`

- GET /api/profile → 200, `data["seller"]["name_en"]` non-empty, catalog list non-empty
- PUT roundtrip: monkeypatch env `QP_PROFILE_STORE` to `tmp_path/"p.json"`;
  GET current profile, change `seller.name_en` to "Acme Ltd", PUT it → 200;
  GET again → name_en == "Acme Ltd". (Import quotepilot.web.app client like
  tests/test_web.py does: `client = TestClient(app)`.)
- PUT with `{"seller": {}}` → 422
- POST /api/profile/import with `{"url": "ftp://x"}` → 422
