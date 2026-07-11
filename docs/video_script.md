# QuotePilot — demo video script & storyboard (<3 min)

Target: **2:40**. Animation-forward. Bilingual: on-screen captions EN + 中文;
voiceover from **`qwen3-tts-flash`** (`language_type:"Auto"`). Core demo is a
**real screen recording** of the live app (never AI-generated product footage).

**Assets to generate with Qwen first (see docs/media_plan.md):**
- VO audio: run each `VO` line below through `qwen3-tts-flash` (one bilingual pass).
- Title card + 3 section slides: `qwen-image-2.0` (prompts in §A, §D, §H).
- Optional 4s intro sting: `wan2.6-i2v` animating the QuotePilot logo.
- Motion assets we already own: the animated architecture reel
  (`docs/architecture.html`) and the app's own in-product animations.

Record at 1920×1080, 30fps. Assemble in ffmpeg or CapCut. Burn in the captions.

---

## Shot list

### A · Cold open — title sting (0:00–0:08)
- **Visual:** 4s `wan` logo sting → hard cut to the title card (Qwen-image):
  "QuotePilot" + "报价领航" + tagline "Email → approved bilingual quote, on
  autopilot." Deep-blue (#0f4c81), clean.
- **Motion:** logo scales in; tagline types on; subtle particle drift.
- **VO (EN):** "Selling software across the US–China border means turning every
  inquiry email into a bilingual quote — by hand. QuotePilot does it on autopilot."
- **中文字幕:** 跨境卖软件,每封询价邮件都要手工做成双语报价单。QuotePilot 让它全自动。

### B · The problem (0:08–0:22)
- **Visual:** split-screen — left: a Chinese inquiry email; right: a clock
  spinning + a stack of steps (parse → price → FX → legal terms) animating in.
- **Motion:** each manual step stamps in with a red "~15 min" tag; they pile up.
- **VO (EN):** "Read the ask — often in Chinese. Look up pricing. Convert USD to
  CNY at today's rate. Get the arbitration and tax clauses right. One to two
  hours per inquiry — and the mistakes are the expensive kind."
- **中文字幕:** 读懂询价(常是中文)、查价、按今日汇率换算、写对仲裁与税务条款——每单 1-2 小时,出错代价高昂。

### C · Meet QuotePilot — the dashboard (0:22–0:34)
- **Visual:** REAL screen recording — the live dashboard at the demo URL. Cursor
  clicks a Chinese sample, pastes into the inbox, hits "Run Autopilot / 启动自动报价".
- **Motion:** the app's own hover/press states; the run row appears.
- **VO (EN):** "Paste an inquiry — English or Chinese — and hand it to the agent."
- **中文字幕:** 粘贴一封询价邮件(中英文均可),交给智能体。

### D · The pipeline (the animation centerpiece) (0:34–1:00)
- **Visual:** REAL recording of the run page — "The agent is on it" — the six
  stages lighting up in sequence (intake → FX → pricing → risk rules → AI risk
  sweep → drafting), elapsed timer ticking. Then CUT to our animated architecture
  reel (`docs/architecture.html`) for ~8s to show the system: static SPA →
  Alibaba Cloud Function Compute → Qwen models + keyless FX → the gate.
- **Motion:** in-product stage animation + the architecture reel's flowing
  data-particles and sequential stage highlight.
- **VO (EN):** "A six-stage pipeline runs on Alibaba Cloud Function Compute. Three
  Qwen models split the work — a flash model extracts, a coder model maps the
  catalog, and qwen-max writes the bilingual draft. Live exchange rates come from
  a keyless FX feed."
- **中文字幕:** 六阶段流水线跑在阿里云函数计算上。三个 Qwen 模型分工:flash 抽取、coder 匹配目录、qwen-max 起草双语。汇率来自免密接口。
- **On-screen slide (Qwen-image), 2s:** the model-routing table
  (qwen-max / qwen-flash / qwen3-coder-plus).

### E · The human gate (1:00–1:20)
- **Visual:** REAL recording — the approval gate. Show the 6/6 stages complete
  dots, the risk flags (the fapiao warning, bilingual), the deal summary, and the
  live bilingual quote preview rendering in the iframe.
- **Motion:** the gate's amber pulse; risk-flag cards sliding in.
- **VO (EN):** "Then it stops — for exactly one human decision. It surfaces the
  risk flags it found, like a customer asking for a Chinese VAT invoice a US
  entity can't issue, and shows the full bilingual quote."
- **中文字幕:** 然后停下——只需一次人工决定。它列出发现的风险(比如客户要增值税发票,美国主体无法开具),并展示完整双语报价单。

### F · Edit the quote (the "human in control" beat) (1:20–1:42)
- **Visual:** REAL recording — click "✎ Edit quote / 编辑报价". Change a quantity
  (e.g. 80 → 150), click "Recalculate & preview / 重新计算并预览". The TOTAL
  updates ($26,144 → $44,820) and the preview re-renders.
- **Motion:** the number counting up; the preview refreshing.
- **VO (EN):** "The operator stays in control — adjust quantities, prices, or
  discounts. The server re-prices with exact decimal math and re-renders. The
  model never touches the numbers."
- **中文字幕:** 操作员始终掌控——改数量、单价、折扣。服务器用精确 Decimal 重算并重新渲染。模型永远不碰数字。

### G · Approve → artifacts (1:42–1:58)
- **Visual:** REAL recording — click "Approve & issue / 批准并出具报价". The
  "Approved & issued" banner; the artifact chips (quote HTML, reply email, JSONs);
  the token count. Quickly open the rendered bilingual quote PDF/HTML in a tab.
- **Motion:** the green banner sweep; chips popping in.
- **VO (EN):** "Approve, and out come a formal bilingual quotation and a
  ready-to-send reply email — with a full audit trail. The whole run cost a few
  thousand Qwen tokens."
- **中文字幕:** 批准后,正式双语报价单和可直接发送的回复邮件即刻生成,并留有完整审计记录。整个运行只花了几千 Qwen tokens。

### H · The twist — built by Qwen (1:58–2:22)
- **Visual:** section slide (Qwen-image) "Built by Qwen, reviewed by a human" →
  quick screen-capture montage: the `scripts/qwen_dev.py` harness, a task spec,
  the ledger file showing "<$1 / $40".
- **Motion:** terminal text typing; ledger total ticking up but staying under $1.
- **VO (EN):** "One more thing. QuotePilot isn't just powered by Qwen — it was
  largely written by Qwen. A small harness dispatched coding tasks to
  qwen3-coder-plus and qwen-max while a supervising agent reviewed every output.
  Total build cost: under one dollar."
- **中文字幕:** 还有一点:QuotePilot 不只是由 Qwen 驱动,它本身大多也是 Qwen 写的。一个小型调度器把编码任务派给 qwen3-coder-plus 和 qwen-max,由监督智能体审查每份产出。总构建成本:不到一美元。

### I · The principle + close (2:22–2:40)
- **Visual:** full-screen line on brand background: "Language to the models.
  Ledgers to the code." → the two safety chips (Decimal / fixed legal terms) →
  end card with the live URL + repo + "powered by Qwen on Alibaba Cloud."
- **Motion:** the line snaps in; chips settle; URL underlines.
- **VO (EN):** "The rule that makes it trustworthy: language to the models,
  ledgers to the code. QuotePilot — powered by Qwen, on Alibaba Cloud."
- **中文字幕:** 让它可信的原则:语言交给模型,账目交给代码。QuotePilot——由 Qwen 驱动,运行在阿里云。

---

## VO-only script (paste into qwen3-tts-flash, `language_type:"Auto"`)
> You can do EN-only VO with 中文 captions (cleaner), or a bilingual VO by
> appending each 中文 line. For a single-voice EN track, feed these lines in order:

1. Selling software across the US–China border means turning every inquiry email into a bilingual quote — by hand. QuotePilot does it on autopilot.
2. Read the ask — often in Chinese. Look up pricing. Convert US dollars to yuan at today's rate. Get the arbitration and tax clauses right. One to two hours per inquiry, and the mistakes are the expensive kind.
3. Paste an inquiry — English or Chinese — and hand it to the agent.
4. A six-stage pipeline runs on Alibaba Cloud Function Compute. Three Qwen models split the work — a flash model extracts, a coder model maps the catalog, and qwen-max writes the bilingual draft. Live exchange rates come from a keyless feed.
5. Then it stops — for exactly one human decision. It surfaces the risk flags it found, like a customer asking for a Chinese VAT invoice a US entity can't issue, and shows the full bilingual quote.
6. The operator stays in control — adjust quantities, prices, or discounts. The server re-prices with exact decimal math and re-renders. The model never touches the numbers.
7. Approve, and out come a formal bilingual quotation and a ready-to-send reply email, with a full audit trail. The whole run cost a few thousand Qwen tokens.
8. One more thing. QuotePilot isn't just powered by Qwen — it was largely written by Qwen. A small harness dispatched coding tasks to Qwen models while a supervising agent reviewed every output. Total build cost: under one dollar.
9. The rule that makes it trustworthy: language to the models, ledgers to the code. QuotePilot — powered by Qwen, on Alibaba Cloud.

## Recording checklist
- [ ] Set the app language toggle to show the flow you're narrating (EN VO → EN UI is cleanest; do a second pass with 中文 UI for b-roll).
- [ ] Pre-warm the backend (hit the URL once) so the demo doesn't cold-start on camera.
- [ ] Pre-seed one archived run so the dashboard isn't empty.
- [ ] Record the architecture reel (`docs/architecture.html`) full-screen for one full loop (~12s) — grab the cleanest 8s.
- [ ] Keep each real-app segment tight; speed-ramp the 15–25s pipeline wait to ~4s.
