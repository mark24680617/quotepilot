# Task T2-revision: fix review findings in the QuotePilot dashboard templates

Your previous submission (below) was reviewed and REJECTED with the following
findings. Re-emit ALL THREE files, complete and corrected. The original task
spec (design system, contexts, layout requirements) still applies exactly.

## Review findings (must ALL be fixed)

1. **BLOCKER — invalid Jinja2 syntax.** `{% if any(flag.severity == 'block' for
   flag in s.risk_flags) %}` is a Python generator expression; Jinja2 raises
   TemplateSyntaxError. Use a Jinja-native form, e.g.
   `{% set blocked = s.risk_flags | selectattr('severity', 'equalto', 'block') | list %}`
   once, then `{% if blocked %}`.
2. **BLOCKER — sample buttons submit the form.** The sample-loading buttons are
   inside `<form>` without `type="button"`, so clicking them submits an empty
   form. Add `type="button"`.
3. **Status/decision colors never resolve.** You emit
   `style="background: var(--status-{{ s.status }})"` but statuses include
   `awaiting_approval` and `failed`, and archive decisions are `approve` /
   `reject` — none of those CSS variables exist. Replace inline style with
   classes: `<span class="badge st-{{ s.status }}">` and
   `<span class="badge st-{{ a.decision }}">`, and define in base.html:
   `.st-running`, `.st-awaiting_approval`, `.st-approved`, `.st-rejected`,
   `.st-failed`, `.st-approve` (= approved color), `.st-reject` (= rejected
   color), plus a default `.badge` (white text, border-radius 999px,
   padding 2px 10px, font-size 12px).
4. **Polling JS cannot update the checklist.** The `<li>` elements carry no
   stage-name identifier, so `querySelector('[class*=...]')` matches nothing;
   you also strip existing `done` classes every tick. Give each stage
   `<li id="stage-intake">` … `<li id="stage-drafting">` and in the poll
   handler do `data.stages.forEach(n => document.getElementById('stage-' + n)?.classList.add('done'))`.
   Never remove classes. Define `.done` styling (green check ✅ shown via
   `li::before`: ⏳ default, ✅ when `.done`).
5. **Component CSS missing.** base.html defines layout only — `table`,
   `th/td`, `textarea` (width 100%, monospace, padding), `button` (primary =
   accent background; `.btn-approve` green #15803d; `.btn-reject` red
   #b91c1c; disabled = gray), `.badge`, `.chip` (severity chips `sev-info`,
   `sev-warn`, `sev-block`), `pre` (soft background, overflow-x auto),
   `.error-box`, card sections (white background, border, radius 10px,
   padding 16-20px, margin-bottom 20px) are all unstyled. Add them.
   Apply `class="btn-approve"` / `class="btn-reject"` to the decision buttons
   and `class="chip sev-{{ flag.severity }}"` to severity chips.
6. **Broken table + None rendering on the dashboard.** The archive table
   renders a 7th `<td>` only when `has_html` — add a 7th header 报价单 Quote
   and ALWAYS render the cell (link or `—`). Everywhere a value can be None
   (`quote_number`, `total_usd`, `company`, `ts`, `decision`) render
   `{{ x or '—' }}`; never show "None" or "$None" (only prefix $ when the
   value exists: `{% if s.total_usd %}${{ s.total_usd }}{% else %}—{% endif %}`).

Also keep: brand header links to `/`; wrap each major section in a card.

## Your previous submission to fix

### base.html
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuotePilot 🛩️</title>
    <style>
        :root {
            --ink: #1a1d24;
            --muted: #6b7280;
            --line: #e5e7eb;
            --accent: #0f4c81;
            --soft: #f4f6f9;
            --status-running: #b45309;
            --status-awaiting: #b91c1c;
            --status-approved: #15803d;
            --status-rejected: #6b7280;
            --severity-info: #0f4c81;
            --severity-warn: #b45309;
            --severity-block: #b91c1c;
        }
        body {
            font-family: "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
            color: var(--ink);
            background: var(--soft);
            margin: 0;
            padding: 0;
        }
        .header {
            position: sticky;
            top: 0;
            background: white;
            border-bottom: 1px solid var(--line);
            z-index: 1000;
        }
        .header .brand {
            display: flex;
            align-items: center;
            padding: 1rem;
            max-width: 1080px;
            margin: 0 auto;
        }
        .header .brand h1 {
            margin: 0;
            font-size: 1.5rem;
            color: var(--accent);
        }
        .header .brand p {
            margin: 0;
            font-size: 0.875rem;
            color: var(--muted);
        }
        .content {
            max-width: 1080px;
            margin: 0 auto;
            padding: 2rem;
        }
        .footer {
            text-align: center;
            padding: 1rem;
            border-top: 1px solid var(--line);
            color: var(--muted);
        }
        .footer a {
            color: var(--accent);
            text-decoration: none;
        }
        .footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="brand">
            <h1>QuotePilot 🛩️</h1>
            <p>LUQ LABS · email → bilingual quote autopilot · powered by Qwen on Alibaba Cloud</p>
        </div>
    </div>
    <div class="content">
        {% block content %}{% endblock %}
    </div>
    <div class="footer">
        Rates by <a href="https://exchangerate-api.com">Exchange Rate API (exchangerate-api.com)</a>
    </div>
    {% block scripts %}{% endblock %}
</body>
</html>

```

### dashboard.html
```html
{% extends "base.html" %}

{% block content %}
    <h2>收件箱 Inbox</h2>
    <form method="post" action="/submit">
        <div id="sample-buttons">
            {% for sample in samples %}
                <button onclick="fetchSample('{{ sample }}')">加载示例 {{ sample }}</button>
            {% endfor %}
        </div>
        <textarea name="email_text" rows="10" id="email-text"></textarea>
        <button type="submit">启动自动报价 Run Autopilot</button>
    </form>

    <h2>进行中 Active</h2>
    {% if submissions %}
        <table>
            <thead>
                <tr>
                    <th>sID</th>
                    <th>公司 Company</th>
                    <th>报价单号 Quote Number</th>
                    <th>总金额 USD Total</th>
                    <th>状态 Status</th>
                    <th>创建时间 Created At</th>
                </tr>
            </thead>
            <tbody>
                {% for s in submissions %}
                    <tr>
                        <td><a href="/s/{{ s.sid }}">{{ s.sid }}</a></td>
                        <td>{{ s.company or '—' }}</td>
                        <td>{{ s.quote_number }}</td>
                        <td>${{ s.total_usd }}</td>
                        <td><span class="badge" style="background: var(--status-{{ s.status }})">{{ s.status }}</span></td>
                        <td>{{ s.created_at }}</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>没有正在进行的提交。 No active submissions.</p>
    {% endif %}

    <h2>历史运行 Archive</h2>
    {% if archived %}
        <table>
            <thead>
                <tr>
                    <th>运行 ID Run ID</th>
                    <th>报价单号 Quote Number</th>
                    <th>公司 Company</th>
                    <th>总金额 USD Total</th>
                    <th>决策 Decision</th>
                    <th>时间 Timestamp</th>
                </tr>
            </thead>
            <tbody>
                {% for a in archived %}
                    <tr>
                        <td>{{ a.run_id }}</td>
                        <td>{{ a.quote_number }}</td>
                        <td>{{ a.company }}</td>
                        <td>${{ a.total_usd }}</td>
                        <td><span class="badge" style="background: var(--status-{{ a.decision }})">{{ a.decision }}</span></td>
                        <td>{{ a.ts }}</td>
                        {% if a.has_html %}
                            <td><a href="/artifacts/{{ a.run_id }}/{{ a.quote_number }}.html">报价单 Quote</a></td>
                        {% endif %}
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>没有历史记录。 No archived runs.</p>
    {% endif %}
{% endblock %}

{% block scripts %}
    <script>
        function fetchSample(name) {
            fetch(`/sample/${name}`)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('email-text').value = data.text;
                });
        }
    </script>
{% endblock %}

```

### submission.html
```html
{% extends "base.html" %}

{% block content %}
    <h2>运行 Run {{ s.sid }} <span class="badge" style="background: var(--status-{{ s.status }})">{{ s.status }}</span></h2>

    <h3>流程进度 Pipeline Progress</h3>
    <ul>
        <li class="{% if 'intake' in s.stages %}done{% endif %}">解析询价 intake</li>
        <li class="{% if 'fx' in s.stages %}done{% endif %}">实时汇率 fx</li>
        <li class="{% if 'pricing' in s.stages %}done{% endif %}">目录定价 pricing</li>
        <li class="{% if 'risk_rules' in s.stages %}done{% endif %}">规则风控 risk_rules</li>
        <li class="{% if 'risk_llm_sweep' in s.stages %}done{% endif %}">AI 风控扫描 risk_llm_sweep</li>
        <li class="{% if 'drafting' in s.stages %}done{% endif %}">双语起草 drafting</li>
    </ul>

    {% if s.status == "running" %}
        <p>自动驾驶运行中… Autopilot running…</p>
        <script>
            setInterval(() => {
                fetch(`/s/{{ s.sid }}/state`)
                    .then(response => response.json())
                    .then(data => {
                        if (data.status !== "running") {
                            location.reload();
                        } else {
                            const stages = document.querySelectorAll('.done');
                            stages.forEach(stage => stage.classList.remove('done'));
                            data.stages.forEach(stage => {
                                const elem = document.querySelector(`[class*="${stage}"]`);
                                if (elem) elem.classList.add('done');
                            });
                        }
                    });
            }, 1500);
        </script>
    {% elif s.status == "awaiting_approval" %}
        <h3>风险标志 Risk Flags</h3>
        <ul>
            {% for flag in s.risk_flags %}
                <li>
                    <span class="chip" style="background: var(--severity-{{ flag.severity }})">{{ flag.severity }}</span>
                    <span>{{ flag.message_zh }}</span>
                    <small>{{ flag.message_en }}</small>
                </li>
            {% endfor %}
        </ul>
        {% if summary %}
            <pre>{{ summary }}</pre>
        {% endif %}
        <iframe src="/s/{{ s.sid }}/preview" style="width:100%;height:520px;border:1px solid var(--line);border-radius:8px"></iframe>
        <form method="post" action="/s/{{ s.sid }}/decision">
            <input type="text" name="notes" placeholder="备注 Notes (optional)">
            <button type="submit" name="action" value="approve" {% if any(flag.severity == 'block' for flag in s.risk_flags) %}disabled{% endif %}>批准并生成 Approve & Render</button>
            <button type="submit" name="action" value="reject">拒绝 Reject</button>
            {% if any(flag.severity == 'block' for flag in s.risk_flags) %}
                <p>⛔ 存在阻断级风险,不可批准 Blocking flag — approval disabled</p>
            {% endif %}
        </form>
    {% elif s.status in ("approved", "rejected") %}
        <p>{% if s.status == "approved" %}已批准 Approved{% else %}已拒绝 Rejected{% endif %}</p>
        <ul>
            {% for artifact in s.artifacts %}
                <li>
                    <a href="/artifacts/{{ artifact.run_id }}/{{ artifact.filename }}">
                        {% if artifact.kind == "quote_html" %}报价单 Quote HTML{% endif %}
                        {% if artifact.kind == "reply_email" %}回复邮件 Reply Email{% endif %}
                        {% if artifact.kind == "quote_json" %}Quote JSON{% endif %}
                        {% if artifact.kind == "inquiry" %}Inquiry JSON{% endif %}
                        {% if artifact.kind == "summary" %}Summary{% endif %}
                    </a>
                </li>
            {% endfor %}
        </ul>
        <p>本次运行消耗 {{ s.tokens }} tokens</p>
    {% elif s.status == "failed" %}
        <div class="error-box">
            <p>错误 Error: {{ s.error }}</p>
        </div>
    {% endif %}

    <a href="/">← 返回 Dashboard</a>
{% endblock %}

```

Output all three complete corrected files with `### FILE:` headers as before.
