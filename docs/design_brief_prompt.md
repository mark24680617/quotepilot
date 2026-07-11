# UI redesign prompt (paste into Claude design / claude.ai)

---

Design and build a complete, production-grade single-file web UI (one
self-contained `index.html`: inline CSS + vanilla JS, zero external resources,
no build step) for **QuotePilot** — an AI "autopilot" that turns cross-border
B2B inquiry emails into approved bilingual (English/中文) price quotes, with
exactly one human approval per run.

## Product story (what the UI must convey)

A sales operator at a company selling cross-border (e.g., US software vendor →
Chinese enterprise buyers) pastes an inbound inquiry email. An agent pipeline
running on Alibaba Cloud (powered by Qwen models) extracts the request, prices
it against a product catalog with live USD/CNY FX, flags business/legal/tax
risks, drafts a bilingual quote — then **pauses for the human to approve**.
On approval it renders a formal bilingual quotation document and a reply-email
draft. The feeling should be: *a calm, trustworthy cockpit for supervising an
autonomous colleague* — professional B2B, bilingual by design, with one
dramatic moment (the approval gate) treated as the hero interaction.

## Hard technical contract (must keep exactly)

- Single file, works when hosted as a static page (GitHub Pages) cross-origin
  against a JSON API. API base:
  `const API = localStorage.getItem("QP_API") || "https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run";`
- NEVER navigate the browser to API URLs (the backend's system domain
  force-downloads HTML) — always fetch() and render. The quote-document
  preview is fetched as text and shown via `<iframe srcdoc=…>`.
- Escape every server-provided string before HTML insertion (an `esc()`
  helper), except the preview HTML which goes only into iframe srcdoc.
- Hash routing: `#/` dashboard · `#/s/{sid}` run detail · `#/settings`.
- Endpoints (JSON unless noted):
  - `GET  /api/bootstrap` → `{samples:[name…], submissions:[SubView…], archived:[Run…]}`
  - `GET  /sample/{name}` → `{name, text}`
  - `POST /api/submit` `{email_text}` → `{sid}` (422 if < 20 chars)
  - `GET  /api/s/{sid}` → `{s: SubView, summary: string|null}` (404 = state recycled)
  - `POST /api/s/{sid}/decision` `{action:"approve"|"reject", notes}` → `{ok,status}` (409 = blocked)
  - `GET  /s/{sid}/state` → `{status, stages:[…]}` (cheap 1.5s poll while running)
  - `GET  /s/{sid}/preview` → HTML text of the quote document
  - `GET  /artifacts/{run_id}/{filename}` → file bytes (open via Blob URL)
  - `GET  /api/profile` / `PUT /api/profile` → CompanyProfile (see below)
  - `POST /api/profile/import` `{url}` → `{draft: CompanyProfile, needs_price:[…], note}` (slow: 15-30s)
- SubView: `{sid, status: running|awaiting_approval|approved|rejected|failed,
  created_at, stages:[…], company, quote_number, total_usd, total_cny,
  risk_flags:[{code, severity: info|warn|block, message_en, message_zh}],
  artifacts:[{kind, run_id, filename}], tokens, error}` — any field nullable.
- Pipeline stages in fixed order (bilingual labels): intake 解析询价 ·
  fx 实时汇率 · pricing 目录定价 · risk_rules 规则风控 · risk_llm_sweep AI 风控扫描 ·
  drafting 双语起草.
- CompanyProfile: `{seller:{name_en,name_zh,jurisdiction_en,jurisdiction_zh,
  website,email,description}, terms:{payment_en/zh, legal_en/zh, tax_note_en/zh},
  rules:{quote_validity_days, wire_threshold_usd, max_extra_discount_pct,
  urgent_deadline_days, quote_prefix}, catalog:[{sku,name_en,name_zh,
  description_en,description_zh,unit,unit_zh,unit_price_usd,
  volume_discounts:[{min_qty,pct}]}]}`.
- Resilience (must keep): poll failures show an inline "reconnecting" hint and
  keep polling (≤20 consecutive fails); 404 on run detail = friendly
  "serverless instance recycled, please resubmit" card; bootstrap auto-retries
  3× with backoff for cold starts (first hit can take ~5s).

## Views & flows

1. **Dashboard `#/`** — hero inbox: paste email or one-click load of 3 bundled
   sample inquiries (2 EN, 1 ZH); primary CTA 启动自动报价 Run Autopilot.
   Below: Active runs (live-updating list) and Archive (past runs; view quote
   HTML via Blob).
2. **Run detail `#/s/{sid}`** — the centerpiece. Running: an animated pipeline
   visual (6 stages progressing, feels alive, ~15-25s total). Awaiting
   approval: risk flags (severity-coded, bilingual), plain-text deal summary,
   embedded quote-document preview, notes field, and the two decision buttons
   (approve disabled + explained when any `block` flag). Approved/rejected:
   outcome banner, artifact chips (quote HTML, reply email, JSONs), token
   count. Failed: error card.
3. **Settings `#/settings`** — company onboarding: "✨ import from website"
   (URL → AI reads the site → prefills company + catalog; slow, needs a
   充满期待的 loading state; never overwrites legal terms), company identity
   form, terms & rules form, editable catalog table (volume discounts in
   compact `50:8, 100:12` syntax), sticky save bar, demo-persistence note.

## Design direction

- Premium bilingual B2B console. 中文 first, English as secondary text — treat
  bilingualism as a designed feature (consistent type pairing for CJK+Latin),
  not an afterthought.
- Evolve, don't keep, the current look: deep-blue accent (#0f4c81 heritage —
  you may refine the palette around it), light UI, generous whitespace, card
  architecture, crisp data tables, refined status/severity color system.
  Aim for the polish level of Linear/Stripe dashboards; avoid generic
  AI-slop gradients-on-everything.
- Micro-interactions: stage progression animation, approval button press
  states, save toast, skeleton/shimmer for loading, cold-start humor line.
- Responsive down to 390px; the quote preview and tables scroll internally.
- Footer must include: "Backend: Alibaba Cloud Function Compute
  (ap-southeast-1)" and "Rates by Exchange Rate API
  (https://www.exchangerate-api.com)" attribution.

Deliver the complete `index.html`.
