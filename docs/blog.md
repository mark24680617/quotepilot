# I had Qwen build a Qwen-powered app — and sat in the reviewer's chair

Most hackathon posts are about what the AI *does*. This one is also about who
*wrote it*. **QuotePilot** — an autopilot that turns a cross-border B2B inquiry
email into an approved, bilingual (EN/中文) price quote — is powered by Qwen at
runtime. But the app itself was also largely *written* by Qwen models, dispatched
through a tiny harness while I sat in the reviewer's chair and accepted or
rejected each piece. Total model spend for the whole build: **under $1 of the
$40 hackathon credit.**

Here's what that actually felt like, where it was magic, and where I had to keep
both hands on the wheel.

- **Live demo:** https://mark24680617.github.io/quotepilot/
- **Repo:** https://github.com/mark24680617/quotepilot

## The problem is boring, expensive, and perfect for an agent

A US software company selling into China answers every inquiry email by hand:
read the ask (often in Chinese), look up pricing, apply volume discounts,
convert USD⇄CNY at today's rate, and draft a bilingual quote with the *right*
cross-border legal and tax terms (HKIAC arbitration, Chinese text controlling,
"we can't issue a fapiao" note). It's 1–2 hours per inquiry, and the mistakes —
a wrong rate, a missing tax clause — are the expensive kind.

That's a real workflow with a real brake pedal built in: someone always reviews
the quote before it goes out. So the design wrote itself — an agent that does
the whole run in under a minute and **pauses for exactly one human decision.**

## The routing: language to the models, ledgers to the code

QuotePilot runs a six-stage pipeline — intake → live FX → pricing → rule risk →
AI risk sweep → bilingual drafting — then stops at a human gate. Three Qwen
models split the work:

| Role | Model |
|---|---|
| Planner / bilingual drafting | `qwen-max` |
| Extraction + risk-sweep workers | `qwen-flash` |
| Strict structured output (catalog mapping) | `qwen3-coder-plus` |

The single most important line I drew: **the LLM never does arithmetic and never
writes legal terms.** Every price is Python `Decimal`, computed in code. Every
legal clause is fixed, lawyer-shaped bilingual text. The model chooses *which*
catalog item a customer meant and writes a warm cover letter — it never decides
that 150 × $290 × 0.92 = $40,020. That's not a stylistic preference; it's the
difference between a demo and something you'd let touch a contract.

```python
# The model maps "we want CitizenReady for 150 seats" → SKU CR-ENT.
# The code does the money — always.
net = (unit_price * qty * (100 - discount_pct) / 100).quantize(CENT, ROUND_HALF_UP)
```

## Letting Qwen write the code

I built a ~150-line dispatcher (`scripts/qwen_dev.py`): hand it a task spec, it
sends the spec to a chosen Qwen model, parses the returned files into a staging
area, and appends token usage to a ledger. Nothing lands in the repo until I
review it. Over the build, Qwen wrote the FastAPI backend, the approval
dashboard, the settings UI, the runs index, and more — fourteen dispatches,
**$0.81 total**, a few cents each. Even the demo video's voiceover is Qwen
(`qwen3-tts-flash`).

The pattern that emerged: **describe the interfaces precisely, and a code model
fills them in impressively well.** When my task spec pinned down exact function
signatures, endpoint shapes, and data models, `qwen3-coder-plus` produced code
that dropped in with only small fixes. When I was vague, I got plausible code
that missed the contract.

## The war stories (nobody's build is clean)

**Alibaba Cloud's `fcapp.run` domain force-downloads HTML.** My first deploy
worked in `curl` but the browser downloaded the page instead of rendering it —
the system domain sets `Content-Disposition: attachment` and forbids 3xx
redirects (anti-phishing). The fix reshaped the architecture for the better: a
static single-page app on GitHub Pages that talks to a CORS-enabled JSON API on
Function Compute. `fetch()` doesn't care about the download header, and now the
judges see a clean HTTPS page whose every request visibly hits the Alibaba Cloud
backend.

**`custom.debian10` ships Python 3.7, not 3.10.** The docs promised 3.10. An
in-instance probe said otherwise. Switching the runtime to `custom.debian12`
(Python 3.11) — and re-vendoring the wheels for cp311 manylinux — fixed the cold
starts.

**Don't ask a code model to re-emit a 70 KB file.** For one big frontend change
I asked Qwen to return the whole updated `index.html`. It gave me back a file
*23 KB smaller* — it had silently dropped an entire settings module and never
implemented the feature I asked for. Lesson learned: give a code model the
**changed functions**, not the whole file, and diff the result. I hand-wrote
that feature instead.

**An adversarial review round caught 11 real bugs.** Before shipping the
multi-company refactor, I ran a small multi-agent review — finders proposing
bugs, independent verifiers trying to *refute* each one. It surfaced a
discount-field name mismatch that would have 422'd every settings save, and a
stored-XSS in a free-text config field. Both would have shipped. Verified
findings only; the skeptics killed the noise.

**Filming the demo caught the best bug of all.** The demo video is recorded
programmatically (Playwright drives the real app; ffmpeg cuts each scene to the
voiceover). While reviewing the edit-then-approve scene frame by frame, I
noticed the issued quote document still showed the *pre-edit* numbers — the
orchestrator was rendering the quote object it held before the human gate,
while the edit endpoint had replaced the gate's copy. On-screen: totals said
$32,550, the artifact said $21,930. One-line fix, a regression test, redeploy —
and a new rule: **watch your own demo like a judge would.**

## The human gate is the product

It would have been easy to make QuotePilot fully autonomous and call it a day.
The interesting product decision was the opposite: make the pause *good*. The
operator sees the drafted quote, the risk flags, and a plain-language summary,
and can **approve, reject, or edit** — adjust quantities, prices, discounts,
add or remove line items. When they edit, the server re-prices in `Decimal` and
re-renders the document; approve then issues exactly what they saw. A `block`
-severity risk flag disables approval outright.

Autonomy with a brake. For a document that becomes a contract, that's the whole
ballgame — and it's what I'd want a judge to remember.

## What "AI writes, human reviews" actually feels like

It's genuinely great at **mechanical breadth** — CRUD endpoints, form UIs,
wiring, tests-to-spec — and it's fast and cheap at it. It is *not* the place to
hand over **money math, security-sensitive parsing, or large-file surgery**;
those are exactly where a confident-but-wrong output costs you. The reviewer's
job isn't ceremony. It's knowing which outputs to trust on sight and which to
read line by line — and never letting the model near the ledger.

Qwen built most of QuotePilot. I made sure it never did the math.

---

**Try it:** https://mark24680617.github.io/quotepilot/ (demo login:
`judge` / `qwen2026`) · **Code:** https://github.com/mark24680617/quotepilot
