# Task T2: Jinja2 templates for the QuotePilot approval dashboard

Produce three Jinja2 templates for a FastAPI app (served with
`fastapi.templating.Jinja2Templates`). Bilingual UI: Chinese labels first,
English second (e.g. "审批 Approve"). Professional B2B tool aesthetic.

## Design system (match the existing quote document)
- CSS variables: `--ink:#1a1d24; --muted:#6b7280; --line:#e5e7eb; --accent:#0f4c81; --soft:#f4f6f9;`
- Font stack: `"Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif`
- Status colors: running `#b45309`, awaiting_approval `#b91c1c` (needs attention), approved `#15803d`, rejected/failed `#6b7280`
- Severity colors: info `#0f4c81`, warn `#b45309`, block `#b91c1c`
- ALL CSS inline in base.html `<style>`. Vanilla JS only. NO external CDNs,
  fonts, or libraries (must work fully offline).
- Header brand: "QuotePilot 🛩️" + subtitle "LUQ LABS · email → bilingual quote autopilot · powered by Qwen on Alibaba Cloud"
- Footer: "Rates by Exchange Rate API (exchangerate-api.com)" attribution link.

## Files to output

### 1. `src/quotepilot/web/templates/base.html`
Blocks: `{% block content %}{% endblock %}` and `{% block scripts %}{% endblock %}`.
Sticky header with brand linking to `/`. Max content width 1080px.

### 2. `src/quotepilot/web/templates/dashboard.html`
Context: `submissions` (list of dicts, newest first), `archived` (list of
objects with attributes: run_id, quote_number, company, total_usd, decision,
ts, has_html), `samples` (list of filenames).

Sections:
1. **收件箱 Inbox** — `<form method="post" action="/submit">` with a
   `<textarea name="email_text" rows="10">` and submit button
   "启动自动报价 Run Autopilot". Above the textarea, one button per entry in
   `samples`: clicking fetches `GET /sample/{name}` (returns JSON
   `{"name","text"}`) and fills the textarea (vanilla JS fetch).
2. **进行中 Active** — table of `submissions`: sid (link to `/s/{sid}`),
   company (or "—"), quote_number, total_usd, status badge, created_at.
   Empty-state text if none.
3. **历史运行 Archive** — table of `archived`: run_id, quote_number, company,
   USD total, decision badge, ts; if has_html, link
   `/artifacts/{run_id}/{quote_number}.html` labeled "报价单 Quote". Empty-state
   text if none.

### 3. `src/quotepilot/web/templates/submission.html`
Context: `s` (dict) and `summary` (string or None).

`s` keys: sid, source, status, created_at, stages (list of completed stage
names), company, quote_number, total_usd, total_cny, risk_flags (list of
{code, severity, message_en, message_zh}), artifacts (list of {kind, run_id,
filename}), tokens, error.

Layout:
1. Title row: "运行 Run {{ s.sid }}" + status badge.
2. **Pipeline progress**: fixed ordered stage list — intake(解析询价),
   fx(实时汇率), pricing(目录定价), risk_rules(规则风控),
   risk_llm_sweep(AI 风控扫描), drafting(双语起草) — each row gets class
   `done` when its name is in `s.stages`, rendered as ✅/⏳.
3. If status == "running": note "自动驾驶运行中… Autopilot running…";
   JS polls `GET /s/{sid}/state` every 1500ms, updates the stage checklist
   from `stages`, and does `location.reload()` when status != "running".
4. If status == "awaiting_approval":
   - Risk flags list: severity chip + message_zh + smaller message_en.
   - `<pre>` with `summary`.
   - `<iframe src="/s/{{ s.sid }}/preview" style="width:100%;height:520px;border:1px solid var(--line);border-radius:8px">`.
   - Decision form: `<form method="post" action="/s/{{ s.sid }}/decision">`
     with optional `<input name="notes">`, a green submit button
     name="action" value="approve" "批准并生成 Approve & Render", and a red
     submit button name="action" value="reject" "拒绝 Reject".
     If ANY flag has severity "block": disable the approve button and show
     "⛔ 存在阻断级风险,不可批准 Blocking flag — approval disabled".
5. If status in ("approved", "rejected"): result banner; artifact links
   `GET /artifacts/{run_id}/{filename}` labeled by kind (quote_html →
   "报价单 Quote HTML", reply_email → "回复邮件 Reply Email", quote_json →
   "Quote JSON", inquiry → "Inquiry JSON", summary → "Summary"); token usage
   line "本次运行消耗 {{ s.tokens }} tokens".
6. If status == "failed": error box with `s.error`.
7. "← 返回 Dashboard" link.
