# Task T11: Devpost submission write-up for QuotePilot

Write the Devpost project description for QuotePilot, a submission to the
"Global AI Hackathon Series with Qwen Cloud" — Track 4 (Autopilot Agent).
Output ONE file: `docs/devpost.md`, in clean Markdown. Professional, concrete,
confident but not hypey. English primary; you MAY include a short 中文 tagline.

## Hard facts (use these; do not invent numbers)
- What it is: an autopilot agent that turns an inbound cross-border B2B inquiry
  email (English OR Chinese) into an approved, bilingual (EN/中文) price quote,
  pausing for exactly ONE human approval.
- Live demo (real, deployed): https://mark24680617.github.io/quotepilot/
- Backend: Alibaba Cloud Function Compute 3.0 (custom.debian12, ap-southeast-1),
  https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run
- Repo (public, MIT): https://github.com/mark24680617/quotepilot
- Pipeline (6 stages): intake (parse email) → live USD/CNY FX → catalog pricing
  → rule-based risk → AI risk sweep → bilingual drafting → HUMAN APPROVAL → render.
- Qwen model routing (via DashScope OpenAI-compatible endpoint): qwen-max =
  planner / bilingual drafting; qwen-flash = extraction + risk sweep workers;
  qwen3-coder-plus = strict structured-output (catalog mapping) + it also WROTE
  most of the app (see "built by Qwen" below).
- Safety design (a differentiator): LLMs NEVER do arithmetic (all money is
  Decimal in code) and NEVER write legal terms (fixed bilingual clauses: HKIAC
  arbitration, Chinese text controlling, no-fapiao tax note). Rule-based risk
  flags are authoritative; a "block" flag disables approval. Full JSONL audit trail.
- Multi-company: seller identity, terms, rules, and catalog live in an editable
  CompanyProfile with an AI "import from your website" onboarding (Qwen reads a
  URL and drafts your company + catalog; legal terms never AI-written).
- Human-in-the-loop is real: the operator can APPROVE, REJECT, or EDIT the quote
  (adjust quantities / prices / discounts, add/remove lines) — the server
  re-prices with Decimal and re-renders before issuing.
- Also implemented an AgentScope 2.0 agent path where the finalize step is gated
  by AgentScope's native permission event (RequireUserConfirmEvent) = the HITL pause.
- "Built by Qwen": the app itself was largely written by Qwen models via a
  dispatch harness (scripts/qwen_dev.py) with a supervising agent reviewing and
  accepting output; total model spend was under $1 of the $40 credit.

## Sections (use these headings)
1. **Inspiration** — the real, expensive manual workflow (US software co. selling
   to Chinese enterprises: parse Chinese email, price, FX, bilingual quote with
   correct cross-border legal/tax terms; 1–2 hrs/inquiry, costly mistakes).
2. **What it does** — the one-run story + the approve/edit/reject gate.
3. **How we built it** — architecture (static SPA on GitHub Pages → fetch JSON
   API → Alibaba Cloud FC → Qwen models + keyless FX), the 6-stage pipeline,
   model routing, and the "built by Qwen" meta-story.
4. **Safety & correctness** — Decimal math, fixed legal terms, authoritative
   risk rules, audit trail. Why this matters for a money/legal document.
5. **Challenges** — real ones: fcapp.run force-downloads HTML (→ static frontend
   + CORS JSON API); custom.debian10 shipped Python 3.7 not 3.10 (→ debian12);
   SSRF-hardening the website-import; keeping Qwen from doing math.
6. **Accomplishments / What's next** — deployed & working end-to-end; editable
   quotes; multi-company onboarding. Next: real email inbox integration, PDF
   export, more currencies.
7. **Built with** — a comma list of tech tags (Qwen / Alibaba Cloud Function
   Compute / DashScope / AgentScope / Python / FastAPI / GitHub Pages / etc.).

Keep it tight and scannable (bullets where useful). ~600-900 words.
