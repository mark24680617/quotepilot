# Qwen Cloud Hackathon — Track 4 (Autopilot Agent)

Project: **Cross-border Email-to-Quote Autopilot Agent** for LUQ LABS (US company selling AI software to Chinese B2B customers).

## Verified facts (2026-07-09)
- Deadline **EXTENDED: July 20, 2026 @ 2:00pm PDT** (was Jul 9). Judging after; winners Aug 7.
- Rubric: Tech Depth 30% / Innovation 30% / Problem Value 25% / Presentation 15%. Stage One = pass/fail viability gate.
- HARD GATES: public OSS repo (with license) + **proof of Alibaba Cloud deployment** (code file link + recording) + architecture diagram + <3-min video + track ID. Local-only = disqualified.
- Blog Post Award ($500 + $500 credits, 10 winners) stacks with track prize — always submit one.
- API endpoint verified working with our key: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` (OpenAI-compatible).
- Models verified: `qwen-max` (planner), `qwen-flash` (workers), `qwen3-coder-plus` (codegen/structured output).
- Key: `./.env` (`QWEN_API_KEY`, $40 credit) — git-ignored, chmod 600. NEVER commit.

## Why Track 4 (decision from 2026-07-03)
Track 3 (Agent Society) requires "measurable efficiency gain over single-agent baselines" — academically contested, needs matched-compute benchmarks; too risky for a solo build. Track 4 rewards a real business workflow, and we own one: LUQ LABS' actual cross-border quoting process.

## Product pipeline (one autopilot run)
1. Ingest inbound customer email (EN or ZH); extract customer, products, quantities, terms, urgency.
2. Retrieve pricing from product catalog (seed JSON/SQLite).
3. Fetch live USD/CNY FX rate; dual-currency pricing with margin rules.
4. Draft bilingual EN/ZH quote: line items, validity, Incoterms, payment (Stripe USD / wire fallback), governing law California, HKIAC arbitration (HK seat), Chinese version controlling (中文为准).
5. Human-in-the-loop checkpoint (AgentScope event bus): summary + risk flags → approve/edit/reject.
6. On approval: render PDF quote + reply email draft; append to audit log.

## Stack
- AgentScope 2.0 (HITL event bus) + AgentScope Runtime → deploy on Alibaba Cloud **Function Compute**.
- Qwen models via DashScope-intl compatible mode.
- Minimal web dashboard (pipeline runs, approvals, audit log) = demo surface for the video.
- Qwen Code CLI as build assistant (good material for the blog post).

## Research findings (2026-07-09, verified by web research)
- **AgentScope**: use `agentscope` v2.0.4 (`pip install agentscope`, Py≥3.11). `agentscope-runtime` is ARCHIVED — its capabilities merged into 2.0; do not use. Built-in HITL: permission system emits `RequireUserConfirmEvent` for unmatched tools under `PermissionMode.DEFAULT`; answer with `UserConfirmResultEvent(reply_id=..., confirm_results=[ConfirmResult(...)])`. Qwen: `DashScopeChatModel(credential=DashScopeCredential(api_key, base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"), model=...)`. v1 `sequential_pipeline`/`MsgHub` no longer exist — chain with plain async Python. **Integrate thin**: one Agent + Toolkit wrapping our stage functions, `render_quote` permission-gated = the HITL demo; embed in our own FastAPI app (built-in Agent Service needs Redis — skip). Fallback to plain-Python HITL if cross-request state fights us past day 2.
- **FC deployment**: FC 3.0 **Web Function** (custom runtime), FastAPI+uvicorn on **0.0.0.0:9000**, region **ap-southeast-1**. Deploy via Serverless Devs: `npm i -g @serverless-devs/s`, `s config add` (needs RAM user AccessKey w/ AliyunFCFullAccess), `s deploy`; auto public URL `https://{random}.ap-southeast-1.fcapp.run`. Vendor deps with `pip install -r requirements.txt -t ./code --platform manylinux2014_x86_64 --only-binary=:all:`. Attach the Python310 public layer for custom runtime. **s.yaml committed to repo = the deployment-proof code file.** Free trial: 150k CU/month × 3 months. Console zip-upload is the fallback path. Do NOT use built-in python3.10 runtime with HTTP trigger for FastAPI.
- **FX APIs** (implemented): primary `open.er-api.com/v6/latest/USD` (check `.result=="success"`, use `rates.CNY` onshore, attribution "Rates By Exchange Rate API" required in UI), fallback `api.frankfurter.dev/v1/latest?base=USD&symbols=CNY` (the old .app domain 301s). exchangerate.host is dead for keyless use. Cache 1–24h.

## Status
- ✅ 2026-07-09: v0.1 committed — full pipeline working E2E with real Qwen calls (3 samples: EN×2, ZH×1; ~4k tokens/run). 11 offline tests green. Intake prompt fixed (services = separate line items); risk sweep de-noised.
- ✅ 2026-07-09: Phase 2 dashboard shipped — FastAPI approval UI (submit → live 6-stage progress → risk flags + quote preview iframe → approve/reject → artifacts). **Dev process: code written by Qwen models via scripts/qwen_dev.py** (qwen3-coder-plus backend / qwen-max templates with 1 revision round / qwen-flash runs index), reviewed & accepted by the orchestrator; ledger docs/qwen_dev_ledger.jsonl, total dev cost so far ≈ $0.07 of the $40 budget. E2E verified over HTTP with a real ZH inquiry run. 21 tests green.
- ✅ 2026-07-10: Phase 2.5 shipped — AgentScope 2.0.4 agent path (`quotepilot agent <file>`): pipeline as FunctionTools, finalize_quote permission-gated → native RequireUserConfirmEvent HITL pause, verified live EN+ZH (allow-rule lets assemble_quote through, exactly one human confirm). Core refactored into `core.py` shared by both paths. Written by qwen3-coder-plus (T4), accepted with 4 fixes.
- ✅ 2026-07-10: Phase 3 prep — FC deployment kit ready: `s.yaml` (fc3 resources layout), `bootstrap`, `deploy/package.sh` (manylinux cp310 vendoring, build verified locally, 43MB), `deploy/README.md` runbook. Serverless Devs CLI installed (~/.local/bin/s). Waiting on user: RAM AccessKey (`s config add`) + Python310 layer ARN → then `s deploy`.
- ✅ 2026-07-10: **DEPLOYED — hard gate cleared.** Live at https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run (FC 3.0, runtime `custom.debian12` = system Python 3.11.2, cp311 vendored wheels, meta-refresh instead of 3xx because fcapp.run forbids redirects). Cloud E2E verified: ZH inquiry → 6 stages → HITL approve → bilingual quote HTML. deployment RAM user's AccessKey configured locally in `~/.s/` (never in the repo).
- ✅ 2026-07-10: **Judge-facing entry live** — fcapp.run force-downloads HTML, so the UI became a static SPA on GitHub Pages (https://mark24680617.github.io/quotepilot/) driving the Alibaba backend via JSON API + CORS (fetch is unaffected by the download policy). Public repo: https://github.com/mark24680617/quotepilot. Full flow verified in a real browser: sample → submit → 6 stages → risk flags → srcdoc quote preview → approve → 5 artifacts (3,465 tokens/run). Newline-escape artifact in qwen-max cover letters fixed.
- ✅ 2026-07-11: **Multi-company** — de-hardcoded LUQ LABS into a CompanyProfile (seller/terms/rules/catalog); Settings UI (#/settings) with editable forms + catalog table + AI "import from website" (Qwen reads a URL → draft profile; legal terms never AI-written). SSRF-hardened (DNS blocklist + metadata IPs + per-hop redirect validation, verified live: ftp/169.254.169.254 → 422). Atomic profile save; bundled default stays pristine (local store gitignored). Adversarial review workflow + revision round fixed 8 frontend + 3 backend findings (discount field name, per-row descriptions, XSS, navToken, live stage checklist). 30 tests green. Dev cost ledger $0.45/$40.
- ✅ 2026-07-11: **UI redesigned** — imported the user's Claude Design build ("QuotePilot AI Autopilot", project b0c36331) via DesignSync get_file. It was a fully-wired SPA (not a mockup): API const, esc(), srcdoc preview, EPOCH nav guards, self-healing /state poll (20-fail cutoff), 404 recycled card, 3× cold-start retry, correct {min_qty,pct} discount serialization — plus a bonus EN/中文 toggle. Verified against the contract (JS syntax, no external resources, all fetches → FC host), deployed to GitHub Pages, browser E2E tested (sample→submit→animated pipeline→approval gate→approve→artifacts). Fixed 3 small bugs post-import: $NaN totals (sub_view returns comma-formatted strings; strip commas before Number()), archive-row Unknown pill (map decision→status), CNY optional in archive.
- ✅ 2026-07-11: **Editable quote** — sales can adjust the quote before issuing. `core.reprice_quote()` (Decimal, server-authoritative) + `POST /api/s/{sid}/edit`; sub_view exposes lines/customer/cover. Frontend: "Edit quote" toggle in the approval gate → editable line-item table (qty/price/discount, add/remove, add-from-catalog), customer fields, cover textareas → "Recalculate & preview" updates totals+summary in place and reloads the doc; Approve issues the edited version. NOTE: the T10 full-file Qwen re-emit failed (dropped 23KB, no feature) — hand-implemented the frontend instead; lesson: don't ask Qwen to re-emit a 70KB+ file, give it the changed functions. Browser E2E verified: 80→150 seats recomputed $26,144→$44,820 live.
- 📋 **Media plan** in docs/media_plan.md (verified Qwen model IDs/pricing): arch diagram = diagram-as-code via qwen; video = real screen recording + qwen3-tts-flash bilingual VO + qwen-image title cards (~$0, free quotas); AI video NOT for product footage; editing via ffmpeg/CapCut.
- ✅ 2026-07-11: Phase 4 drafts done — animated architecture diagram (docs/architecture.html, doubles as static image + video reel), Devpost write-up (docs/devpost.md), blog post (docs/blog.md, hand-written after qwen draft truncated), <3-min animation-forward video storyboard + qwen3-tts VO script (docs/video_script.md). Dev ledger $0.81/$40.
- ⏭ Phase 4 remaining (needs user): record the demo video per the storyboard (real screen recording + qwen3-tts VO + qwen-image title cards), post the blog somewhere public for the Blog Award, fill the Devpost form. Then SUBMIT (deadline Jul 20 2pm PDT; target Jul 19).

## Timeline (11 days)
- Jul 9–10: scaffold + core pipeline (email parse → quote draft) running locally
- Jul 11–12: HITL checkpoint + dashboard
- Jul 13–14: Alibaba Cloud Function Compute deployment + proof recording
- Jul 15–16: polish, architecture diagram, demo seed data (2 EN + 1 ZH sample inquiries)
- Jul 17–18: <3-min video + Devpost description + blog post
- Jul 19: **submit** (1-day buffer before Jul 20 2pm PDT)

## Qwen Code CLI kickoff prompt
```text
You are helping me build my submission for the Qwen Cloud Global AI Hackathon,
Track 4 (Autopilot Agent): an autonomous cross-border email-to-quote agent for
a US software company (LUQ LABS) selling to Chinese B2B customers.

Goal: when a customer inquiry email arrives (English or Chinese), the agent
autonomously produces a ready-to-send bilingual (EN/ZH) price quote and pauses
for exactly one human approval before sending.

Pipeline (single autopilot run):
1. Ingest & classify the inbound email (EN/ZH); extract customer, products,
   quantities, delivery terms, urgency.
2. Retrieve pricing from a product catalog (JSON/SQLite seed data).
3. Fetch the live USD/CNY FX rate; compute dual-currency pricing with
   configurable margin rules.
4. Draft a bilingual quote: line items, validity period, Incoterms, payment
   terms (Stripe/USD, wire fallback), governing law California, HKIAC
   arbitration (Hong Kong seat), Chinese version legally controlling (中文为准).
5. Human-in-the-loop checkpoint: show a summary with risk flags;
   approve / edit / reject.
6. On approval: render a PDF quote + reply email draft; log to an audit trail.

Tech requirements:
- Qwen models via the OpenAI-compatible endpoint
  https://dashscope-intl.aliyuncs.com/compatible-mode/v1 (env QWEN_API_KEY):
  qwen-max as planner/orchestrator, qwen-flash for extraction/classification
  workers, qwen3-coder-plus for structured-output/codegen tasks.
- AgentScope 2.0 for the multi-step agent + HITL event bus; AgentScope Runtime
  for serving; target deployment: Alibaba Cloud Function Compute (deployment
  proof is a hard gate for the hackathon).
- Python 3.11+, MIT license, OSS-ready repo, README with architecture diagram,
  .env.example, no secrets in git.
- A minimal web dashboard showing pipeline runs, HITL approvals, and the audit
  log — this is the demo surface for the video.

Judging: Tech Depth 30% / Innovation 30% / Problem Value 25% / Presentation 15%.
Optimize for one flawless end-to-end autopilot demo over feature count.

Start by scaffolding the repo structure, then implement the pipeline steps in
order, ending with a runnable CLI demo over three sample inquiry emails
(2 English, 1 Chinese).
```
