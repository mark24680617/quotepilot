# QuotePilot — email → approved bilingual quote, on autopilot

**报价领航 · 跨境询价邮件的全自动双语报价助手**

- 🔗 **Live demo:** https://mark24680617.github.io/quotepilot/
- 💻 **Repo (MIT):** https://github.com/mark24680617/quotepilot
- ☁️ **Backend (Alibaba Cloud FC):** https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run
- 🏷️ **Track 4 — Autopilot Agent**

## Inspiration
QuotePilot was inspired by the real, expensive, and time-consuming manual workflow faced by US software companies selling to Chinese enterprises. The process typically involves:

- Parsing inbound emails in either English or Chinese.
- Pricing the requested products or services.
- Converting currency (USD to CNY) using live exchange rates.
- Drafting a bilingual (English and Chinese) price quote with correct cross-border legal and tax terms.
- Reviewing and approving the quote before sending it back to the client.

This manual process can take 1-2 hours per inquiry and is prone to costly mistakes, such as incorrect pricing, wrong legal terms, and miscalculated taxes.

## What it does
QuotePilot automates this entire workflow, turning an inbound cross-border B2B inquiry email into an approved, bilingual (EN/中文) price quote, with exactly one human approval step. Here's how it works in a single run:

1. **Intake**: The system parses the incoming email.
2. **Live USD/CNY FX**: It fetches the latest exchange rate.
3. **Catalog Pricing**: It maps the requested items to the seller's catalog.
4. **Rule-Based Risk**: It applies predefined risk rules.
5. **AI Risk Sweep**: It uses AI to further assess any potential risks.
6. **Bilingual Drafting**: It drafts the quote in both English and Chinese.
7. **HUMAN APPROVAL**: The operator can approve, reject, or edit the quote.
8. **Render**: The final quote is rendered and sent to the client.

The human-in-the-loop step ensures that the operator can make any necessary adjustments, such as changing quantities, prices, or discounts, before the server re-prices and re-renders the quote.

## How we built it
### Architecture
- **Frontend**: A static Single Page Application (SPA) hosted on GitHub Pages.
- **Backend**: Alibaba Cloud Function Compute 3.0 (custom.debian12, ap-southeast-1).
- **API**: A JSON API served by the backend, accessed via CORS from the frontend.
- **Qwen Models**: Integrated via DashScope OpenAI-compatible endpoint.
- **Keyless FX**: Live USD/CNY exchange rates fetched from a keyless API.

### Pipeline
A six-stage agent pipeline, then a human gate, then render:

1. **Intake** — parse the inbound email (EN or 中文).
2. **Live USD/CNY FX** — fetch today's rate (keyless, cached).
3. **Catalog Pricing** — map requests to the seller's catalog.
4. **Rule-Based Risk** — apply deterministic risk rules.
5. **AI Risk Sweep** — an LLM pass for anything the rules missed.
6. **Bilingual Drafting** — draft the cover letter in EN + 中文.

→ **Human gate** (approve / edit / reject) → **Render** the bilingual quote
document + reply-email draft.

We also built an **AgentScope 2.0** agent path where the finalize step is gated
by AgentScope's native permission event (`RequireUserConfirmEvent`) — the same
human-in-the-loop pause, expressed through the framework.

### Model Routing
- **Qwen-Max**: Used for planning and bilingual drafting.
- **Qwen-Flash**: Used for extraction and risk sweep workers.
- **Qwen3-Coder-Plus**: Used for strict structured-output (catalog mapping) and also wrote most of the app.

### "Built by Qwen"
The app itself was largely written by Qwen models via a dispatch harness (`scripts/qwen_dev.py`) with a supervising agent reviewing and accepting output. Total model spend was under $1 of the $40 credit.

## Safety & correctness
- **Decimal Math**: All monetary calculations are done using the `Decimal` type in Python to ensure precision.
- **Fixed Legal Terms**: Fixed bilingual clauses (HKIAC arbitration, Chinese text controlling, no-fapiao tax note) are used, and LLMs never write legal terms.
- **Authoritative Risk Rules**: Rule-based risk flags are authoritative; a "block" flag disables approval.
- **Audit Trail**: Full JSONL audit trail for every step of the process.

These safety measures are crucial for a money and legal document, ensuring that the quotes are accurate, legally sound, and traceable.

## Challenges
- **fcapp.run Force-Download HTML**: Worked around this by using a static frontend and a CORS JSON API.
- **Python Version Mismatch**: Custom.debian10 shipped with Python 3.7 instead of 3.10, so we switched to debian12.
- **SSRF Hardening**: Implemented SSRF hardening for the website-import feature.
- **Preventing LLMs from Doing Math**: Designed the system to prevent LLMs from performing arithmetic, ensuring all calculations are done in code.

## Accomplishments / What's next
- **Deployed & Working End-to-End**: The system is fully deployed and working end-to-end.
- **Editable Quotes**: The operator can edit the quote before finalizing.
- **Multi-Company Onboarding**: Seller identity, terms, rules, and catalog live in an editable CompanyProfile with an AI "import from your website" onboarding.

**What's next**:
- Real email inbox integration.
- PDF export for the final quote.
- Support for more currencies.

## Built with
- Qwen
- Alibaba Cloud Function Compute
- DashScope
- AgentScope
- Python
- FastAPI
- GitHub Pages
- Decimal
- JSONL
- CORS
- Debian 12
- SSRF Hardening
