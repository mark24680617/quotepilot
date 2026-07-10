# QuotePilot 🛩️

**An autopilot agent that turns cross-border B2B inquiry emails into approved, bilingual (EN/中文) price quotes — with exactly one human approval in the loop.**

Built for the [Global AI Hackathon Series with Qwen Cloud](https://qwencloud-hackathon.devpost.com/) — **Track 4: Autopilot Agent**.

## The problem

A US software company selling to Chinese enterprise customers answers every
inquiry email by hand: parse the ask (often in Chinese), look up pricing,
apply volume discounts, convert USD⇄CNY at today's rate, draft a bilingual
quote with the right cross-border legal terms (HKIAC arbitration, Chinese
text controlling, no-fapiao tax notes), and reply. It takes 1–2 hours per
inquiry and mistakes in the legal/tax details are expensive.

QuotePilot does the whole run in under a minute, pauses once for a human
approve/reject, and leaves a full audit trail.

## Pipeline

```
inbound email (EN or 中文)
   │
   ▼
┌─ intake ────────── qwen-flash: extract customer, items, terms, questions
├─ fx ────────────── live USD/CNY (keyless APIs + offline fallback)
├─ pricing ───────── deterministic catalog match → qwen3-coder-plus for
│                    fuzzy mapping (validated in code); Decimal math only
├─ risk ──────────── rule engine (fapiao, wire threshold, discount floor,
│                    deadlines, jurisdiction conflicts) + qwen-flash sweep
├─ drafting ──────── qwen-max: personalized bilingual cover letters &
│                    answers — prices and legal terms are NEVER LLM-written
   ▼
⏸  HUMAN APPROVAL GATE  (approve / edit / reject; blocks can't be approved)
   ▼
artifacts: quote HTML (print-ready) · reply email draft · JSONL audit trail
```

**Model routing (Qwen Cloud, OpenAI-compatible endpoint):**

| Role | Model | Why |
|---|---|---|
| Planner / bilingual drafting | `qwen-max` | best 商务中文 quality |
| Extraction & risk sweep | `qwen-flash` | fast + cheap workers |
| Catalog mapping (strict JSON) | `qwen3-coder-plus` | reliable structured output |

## Quickstart

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env   # put your Qwen API key in
pytest                 # offline tests, no API calls

# run the autopilot on the bundled sample inquiries (interactive approval)
quotepilot run data/samples/*.txt

# demo mode (auto-approve, blocking flags still reject)
quotepilot run data/samples/*.txt --auto-approve

# approval dashboard (submit inquiries, watch the pipeline, approve/reject)
quotepilot web            # http://localhost:9000
```

Each run writes to `runs/<run-id>/`: `inquiry.json`, `quote.json`,
`summary.txt`, `audit.jsonl`, and — after approval — `<quote-number>.html`
and `reply_email.md`.

## Safety design

- **LLMs never do math.** All pricing is `Decimal` arithmetic in code.
- **LLMs never write legal terms.** Payment/arbitration/tax language is
  fixed text from a lawyer-reviewed bilingual contract template.
- **Rule flags are authoritative.** The LLM risk sweep can add advisory
  flags but can never remove rule-based ones; `block` flags disable approval.
- **Full audit trail.** Every stage, decision, and token count is logged.

## License

MIT © 2026 LUQ LABS L.L.C.
