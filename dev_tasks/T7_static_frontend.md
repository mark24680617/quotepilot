# Task T7: static single-file frontend for QuotePilot (GitHub Pages)

Build `docs/index.html` — a fully self-contained static page (inline CSS +
vanilla JS, NO external resources, NO build step) that drives the QuotePilot
backend entirely through its JSON API. It will be hosted on GitHub Pages and
must work cross-origin against the Alibaba Cloud endpoint.

## API base

```js
const API = localStorage.getItem("QP_API")
         || "https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run";
```
All requests via fetch(). CORS is enabled server-side (`*`). IMPORTANT: never
navigate the browser to API URLs (the system domain force-downloads
responses) — always fetch and render.

## API contract (already implemented)

- `GET {API}/api/bootstrap` → `{"samples": ["inquiry_en_1.txt", ...], "submissions": [SubView...], "archived": [Run...]}`
- `GET {API}/sample/{name}` → `{"name": str, "text": str}`
- `POST {API}/api/submit` JSON `{"email_text": str}` → `{"sid": str}` (422 if too short)
- `GET {API}/api/s/{sid}` → `{"s": SubView, "summary": str|null}`
- `POST {API}/api/s/{sid}/decision` JSON `{"action": "approve"|"reject", "notes": str|null}` → `{"ok": true, "status": str}` (409 if blocked)
- `GET {API}/s/{sid}/state` → `{"status": str, "stages": [str...]}` (cheap poll)
- `GET {API}/s/{sid}/preview` → HTML string of the bilingual quote document (fetch as text)
- `GET {API}/artifacts/{run_id}/{filename}` → file bytes (fetch → Blob)

SubView = `{sid, source, status, created_at, stages:[...], company, quote_number,
total_usd, total_cny, risk_flags:[{code,severity,message_en,message_zh}],
artifacts:[{kind,run_id,filename}], tokens, error}` — any field may be null.
Statuses: running / awaiting_approval / approved / rejected / failed.
Stage order (fixed): intake(解析询价), fx(实时汇率), pricing(目录定价),
risk_rules(规则风控), risk_llm_sweep(AI 风控扫描), drafting(双语起草).

## Design system (match the existing product exactly)

- CSS vars: `--ink:#1a1d24; --muted:#6b7280; --line:#e5e7eb; --accent:#0f4c81; --soft:#f4f6f9;`
- Font: `"Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif`; bg var(--soft); content max-width 1080px; white cards (border 1px var(--line), radius 10px, padding 18px, margin-bottom 20px).
- Sticky white header: brand "QuotePilot 🛩️" (accent, links to `#/`) + subtitle "LUQ LABS · email → bilingual quote autopilot · powered by Qwen on Alibaba Cloud".
- Status badge classes: running #b45309, awaiting_approval #b91c1c, approved #15803d, rejected/failed #6b7280 (badge: white text, radius 999px, padding 2px 10px, 12px).
- Severity chips: info #0f4c81, warn #b45309, block #b91c1c.
- Buttons: primary accent; `.btn-approve` #15803d; `.btn-reject` #b91c1c; disabled gray.
- Bilingual labels, Chinese first ("批准并生成 Approve & Render").
- Footer: "Backend: Alibaba Cloud Function Compute (ap-southeast-1) · Rates by <a href=https://www.exchangerate-api.com>Exchange Rate API</a>".

## Behavior (hash router: `#/` dashboard, `#/s/{sid}` submission)

### Dashboard `#/`
1. **收件箱 Inbox** card: sample buttons (from bootstrap.samples; fetch sample text into the textarea on click), `<textarea rows=10>`, submit button "启动自动报价 Run Autopilot" → POST /api/submit → on success `location.hash = "#/s/"+sid`; on error show inline message.
2. **进行中 Active** card: table (sid link→`#/s/{sid}`, company, quote_number, total, status badge, created_at). Empty state text. Refresh every 5s while visible.
3. **历史运行 Archive** card: table of archived (run_id, quote_number, company, $total, decision badge, ts, and if has_html a "报价单 Quote" action that fetches `/artifacts/{run_id}/{quote_number}.html` and opens it via Blob URL in a new tab). Empty state text.

### Submission `#/s/{sid}`
Load /api/s/{sid} then render by status:
- Stage checklist (fixed 6 rows, ⏳→✅ by `stages`), always visible.
- running: "自动驾驶运行中… Autopilot running…", poll `/s/{sid}/state` every 1500ms updating checklist; when status changes → reload full view via /api/s/{sid}.
- awaiting_approval: risk flag list (chip + message_zh + small message_en); `<pre>` summary; quote preview: fetch `/s/{sid}/preview` as text → render in `<iframe>` via the `srcdoc` attribute (height 520px, border var(--line), radius 8px); decision bar: notes input + approve/reject buttons → POST /api/s/{sid}/decision → re-render. If any flag severity=="block": disable approve + show "⛔ 存在阻断级风险,不可批准 Blocking flag — approval disabled". On 409 show the error inline.
- approved/rejected: result banner; artifact list — each artifact fetched via Blob on click and opened in a new tab (label by kind: quote_html→"报价单 Quote HTML", reply_email→"回复邮件 Reply Email", quote_json→"Quote JSON", inquiry→"Inquiry JSON", summary→"Summary"); tokens line "本次运行消耗 {tokens} tokens".
- failed: error box with `s.error`.
- "← 返回 Dashboard" link (`#/`).

### Robustness
- Show a small "API 连接失败,请稍后重试 (cold start may take ~5s)" banner on fetch failure with a retry button; first request after idle may be slow (cold start) — use fetch timeout ~30s via AbortController.
- Escape ALL server-provided strings before inserting into HTML (write a small `esc()` helper) EXCEPT the preview HTML which goes into iframe srcdoc only.
- Clear all polling timers on route change.

## Output
Exactly one file: `docs/index.html`, complete.
