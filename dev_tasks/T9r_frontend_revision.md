# Task T9-revision: fix review findings in docs/index.html

Your previous submission (complete file below) was reviewed and REJECTED.
Re-emit the COMPLETE corrected file. All T9 requirements still apply.

## Findings (fix ALL)

1. **BLOCKER — volume discount field name.** Backend model is
   `{min_qty, pct}`; you used `{min_qty, discount_pct}` in parseDiscounts /
   serializeDiscounts (lines ~476-483). Saving discounts 422s and existing
   discounts render as "50:undefined". Use `pct` everywhere.
2. **BLOCKER — description preservation.** You "preserve"
   description_en/description_zh by row index against the profile loaded at
   render time (lines ~833-840). AI-imported descriptions are discarded and
   row deletion shifts descriptions onto wrong SKUs. Fix per spec: store the
   descriptions ON the row (hidden inputs or data-* attributes populated when
   the row is created — from the loaded profile OR the import draft) and read
   them back per-row on save. New manual rows get "".
3. **XSS in value attributes.** rules.quote_prefix, rules.wire_threshold_usd,
   rules.max_extra_discount_pct, and catalog unit_price_usd are interpolated
   into `value="…"` without esc() (lines ~611, 617, 621, 641, 726). Wrap ALL
   of them (esc() already escapes quotes).
4. **Async retry stomps navigation.** The bootstrap retry loop (and the
   settings loader) continue after awaits without re-checking the route. Give
   each render invocation a token (`const myToken = ++navToken` module
   counter; increment in handleHashChange) and after every await bail out if
   `myToken !== navToken`. Apply to renderDashboard retries, renderSettings
   load, and the import handler's slow await.
5. **Stage checklist never live-updates (pre-existing).**
   `document.querySelector('.card:first-child')` matches nothing (first child
   of the container is the back-link). The stage rows already get ids like
   `stage-intake`? If not, give each stage row `id="stage-{name}"` and in the
   poll handler update via `document.getElementById('stage-'+name)` — add
   class `completed` and swap the icon to ✅. Never rebuild the whole card.
6. **Import timeout too short.** Pass a 90_000ms timeout to fetchWithTimeout
   for POST /api/profile/import only.
7. **Retry schedule.** Spec: 3 retries with 2s/5s/10s backoff = up to 4
   attempts total. Your delays array's 10000 entry is dead. Fix the loop.
8. **NaN on empty numeric inputs.** Empty 单价/数字 fields become NaN → null →
   422 on save. On save: default empty/NaN unit_price_usd to "0.00", validity
   days to 30, urgent days to 7, thresholds to "50000"/"15"; never send NaN.
   Show an inline note listing fields that were defaulted.

## Current file to fix

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
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif;
            background-color: var(--soft);
            color: var(--ink);
            line-height: 1.6;
        }
        
        .header {
            position: sticky;
            top: 0;
            background: white;
            padding: 16px 24px;
            border-bottom: 1px solid var(--line);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .brand {
            font-size: 24px;
            font-weight: bold;
            color: var(--accent);
            text-decoration: none;
        }
        
        .subtitle {
            color: var(--muted);
            font-size: 14px;
        }
        
        .container {
            max-width: 1080px;
            margin: 0 auto;
            padding: 24px;
        }
        
        .card {
            background: white;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 20px;
        }
        
        .card-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 16px;
            color: var(--ink);
        }
        
        .btn {
            background-color: var(--accent);
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            cursor: pointer;
            font-size: 14px;
        }
        
        .btn:hover {
            opacity: 0.9;
        }
        
        .btn:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        
        .btn-approve {
            background-color: #15803d;
        }
        
        .btn-reject {
            background-color: #b91c1c;
        }
        
        .status-badge {
            color: white;
            border-radius: 999px;
            padding: 2px 10px;
            font-size: 12px;
            display: inline-block;
        }
        
        .status-running {
            background-color: #b45309;
        }
        
        .status-awaiting_approval {
            background-color: #b91c1c;
        }
        
        .status-approved {
            background-color: #15803d;
        }
        
        .status-rejected,
        .status-failed {
            background-color: #6b7280;
        }
        
        .severity-info {
            background-color: var(--accent);
            color: white;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 12px;
        }
        
        .severity-warn {
            background-color: #b45309;
            color: white;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 12px;
        }
        
        .severity-block {
            background-color: #b91c1c;
            color: white;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 12px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid var(--line);
        }
        
        th {
            color: var(--muted);
            font-weight: normal;
            font-size: 14px;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        textarea, input[type="text"], input[type="number"] {
            width: 100%;
            padding: 10px;
            border: 1px solid var(--line);
            border-radius: 6px;
            resize: vertical;
        }
        
        .error-message {
            color: #b91c1c;
            margin-top: 8px;
            font-size: 14px;
        }
        
        .success-message {
            color: #15803d;
            margin-top: 8px;
            font-size: 14px;
        }
        
        .warning-banner {
            background-color: #fef3c7;
            color: #b45309;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .reconnect-banner {
            background-color: #dbeafe;
            color: #1e40af;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 16px;
            font-size: 14px;
            text-align: center;
        }
        
        .stage-item {
            display: flex;
            align-items: center;
            padding: 8px 0;
        }
        
        .stage-icon {
            margin-right: 10px;
            font-size: 18px;
        }
        
        .stage-text {
            color: var(--muted);
        }
        
        .completed .stage-text {
            color: var(--ink);
            font-weight: bold;
        }
        
        .preview-frame {
            width: 100%;
            height: 520px;
            border: 1px solid var(--line);
            border-radius: 8px;
        }
        
        .decision-bar {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--line);
        }
        
        .notes-input {
            width: 100%;
            padding: 10px;
            border: 1px solid var(--line);
            border-radius: 6px;
            margin-bottom: 10px;
        }
        
        .block-warning {
            background-color: #fee2e2;
            color: #b91c1c;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: var(--muted);
            font-size: 14px;
        }
        
        .footer a {
            color: var(--accent);
        }
        
        .back-link {
            display: inline-block;
            margin-bottom: 16px;
            color: var(--accent);
            text-decoration: none;
        }
        
        .back-link:hover {
            text-decoration: underline;
        }
        
        .artifact-list {
            margin-top: 16px;
        }
        
        .artifact-item {
            margin-bottom: 8px;
        }
        
        .artifact-btn {
            background-color: #e5e7eb;
            color: var(--ink);
            border: none;
            border-radius: 4px;
            padding: 4px 8px;
            cursor: pointer;
            font-size: 14px;
            margin-right: 8px;
        }
        
        .artifact-btn:hover {
            background-color: #d1d5db;
        }
        
        .tokens-info {
            margin-top: 16px;
            color: var(--muted);
            font-size: 14px;
        }
        
        .empty-state {
            color: var(--muted);
            text-align: center;
            padding: 20px;
        }
        
        .sticky-bottom-bar {
            position: sticky;
            bottom: 0;
            background: white;
            padding: 16px;
            border-top: 1px solid var(--line);
            text-align: center;
            margin-top: 20px;
        }
        
        .demo-note {
            font-size: 12px;
            color: var(--muted);
            margin-top: 8px;
        }
        
        .catalog-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .catalog-table th, .catalog-table td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid var(--line);
        }
        
        .catalog-table input {
            width: 100%;
            padding: 4px;
            border: 1px solid var(--line);
            border-radius: 4px;
        }
        
        .delete-btn {
            background-color: #b91c1c;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 4px 8px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .add-product-btn {
            background-color: #15803d;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 12px;
            cursor: pointer;
            margin-top: 10px;
        }
        
        .import-spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
            margin-right: 8px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="header">
        <a href="#/" class="brand">QuotePilot 🛩️</a>
        <div class="subtitle">LUQ LABS · email → bilingual quote autopilot · powered by Qwen on Alibaba Cloud</div>
        <a href="#/settings" class="subtitle">⚙️ 设置 Settings</a>
    </div>
    
    <div class="container" id="main-container">
        <!-- Content will be injected here -->
    </div>
    
    <div class="footer">
        Backend: Alibaba Cloud Function Compute (ap-southeast-1) · Rates by <a href="https://www.exchangerate-api.com">Exchange Rate API</a>
    </div>

    <script>
        // Configuration
        const API = localStorage.getItem("QP_API") 
                 || "https://quotepilot-kafogbnbjc.ap-southeast-1.fcapp.run";
        
        // Global state
        let currentRoute = null;
        let activeTimers = [];
        
        // Helper functions
        function esc(str) {
            if (typeof str !== 'string') return '';
            return str
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#x27;');
        }
        
        function formatDate(dateStr) {
            return new Date(dateStr).toLocaleString('zh-CN');
        }
        
        function formatCurrency(amount, currency) {
            if (amount === null || amount === undefined) return 'N/A';
            return `${currency} ${Number(amount).toFixed(2)}`;
        }
        
        function getStatusClass(status) {
            switch (status) {
                case 'running': return 'status-running';
                case 'awaiting_approval': return 'status-awaiting_approval';
                case 'approved': return 'status-approved';
                case 'rejected': return 'status-rejected';
                case 'failed': return 'status-failed';
                default: return 'status-failed'; // fallback for unknown statuses
            }
        }
        
        function getSeverityClass(severity) {
            switch (severity) {
                case 'info': return 'severity-info';
                case 'warn': return 'severity-warn';
                case 'block': return 'severity-block';
                default: return 'severity-info';
            }
        }
        
        function clearTimers() {
            activeTimers.forEach(timer => clearInterval(timer));
            activeTimers = [];
        }
        
        function fetchWithTimeout(url, options = {}, timeout = 30000) {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), timeout);
            
            return fetch(url, { ...options, signal: controller.signal })
                .then(response => {
                    clearTimeout(timeoutId);
                    return response;
                })
                .catch(error => {
                    clearTimeout(timeoutId);
                    throw error;
                });
        }
        
        // Parse discount string like "50:8, 100:12" to array of objects
        function parseDiscounts(discountStr) {
            if (!discountStr || discountStr.trim() === '') return [];
            return discountStr.split(',').map(item => {
                const [qty, pct] = item.split(':').map(Number);
                return { min_qty: qty, discount_pct: pct };
            }).filter(d => !isNaN(d.min_qty) && !isNaN(d.discount_pct));
        }
        
        // Serialize discounts array to string like "50:8, 100:12"
        function serializeDiscounts(discounts) {
            if (!Array.isArray(discounts) || discounts.length === 0) return '';
            return discounts.map(d => `${d.min_qty}:${d.discount_pct}`).join(', ');
        }
        
        // Router
        function handleHashChange() {
            const hash = window.location.hash.substring(1);
            
            // Clear previous timers
            clearTimers();
            
            if (hash.startsWith('/s/')) {
                const sid = hash.substring(3);
                renderSubmission(sid);
            } else if (hash === '/settings') {
                renderSettings();
            } else {
                renderDashboard();
            }
        }
        
        // Settings view
        async function renderSettings() {
            currentRoute = 'settings';
            const container = document.getElementById('main-container');
            
            // Show loading state
            container.innerHTML = `
                <div class="card">
                    <h2 class="card-title">加载中 Loading...</h2>
                </div>
            `;
            
            try {
                const response = await fetchWithTimeout(`${API}/api/profile`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const profile = await response.json();
                
                // Build import card
                let importCard = `
                    <div class="card">
                        <h2 class="card-title">✨ AI 导入 Import from website</h2>
                        <div style="display: flex; gap: 10px;">
                            <input type="text" id="import-url" placeholder="输入公司网站 URL Enter company website URL">
                            <button class="btn" id="import-btn">抓取并识别 Fetch & Extract</button>
                        </div>
                        <div id="import-status" style="margin-top: 10px;"></div>
                    </div>
                `;
                
                // Build company info card
                let companyCard = `
                    <div class="card">
                        <h2 class="card-title">公司信息 Company</h2>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div>
                                <label>公司名称 (EN)</label>
                                <input type="text" id="name-en" value="${esc(profile.seller.name_en)}">
                            </div>
                            <div>
                                <label>公司名称 (ZH)</label>
                                <input type="text" id="name-zh" value="${esc(profile.seller.name_zh)}">
                            </div>
                            <div>
                                <label>注册地 (EN)</label>
                                <input type="text" id="jurisdiction-en" value="${esc(profile.seller.jurisdiction_en)}">
                            </div>
                            <div>
                                <label>注册地 (ZH)</label>
                                <input type="text" id="jurisdiction-zh" value="${esc(profile.seller.jurisdiction_zh)}">
                            </div>
                            <div>
                                <label>网站 Website</label>
                                <input type="text" id="website" value="${esc(profile.seller.website || '')}">
                            </div>
                            <div>
                                <label>邮箱 Email</label>
                                <input type="text" id="email" value="${esc(profile.seller.email || '')}">
                            </div>
                        </div>
                        <div style="margin-top: 16px;">
                            <label>公司描述 Description</label>
                            <textarea id="description" rows="3">${esc(profile.seller.description || '')}</textarea>
                        </div>
                    </div>
                `;
                
                // Build terms card
                let termsCard = `
                    <div class="card">
                        <h2 class="card-title">条款与规则 Terms & Rules</h2>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div>
                                <label>付款条款 (EN)</label>
                                <textarea id="payment-en" rows="3">${esc(profile.terms.payment_en || '')}</textarea>
                            </div>
                            <div>
                                <label>付款条款 (ZH)</label>
                                <textarea id="payment-zh" rows="3">${esc(profile.terms.payment_zh || '')}</textarea>
                            </div>
                            <div>
                                <label>法律条款 (EN)</label>
                                <textarea id="legal-en" rows="3">${esc(profile.terms.legal_en || '')}</textarea>
                            </div>
                            <div>
                                <label>法律条款 (ZH)</label>
                                <textarea id="legal-zh" rows="3">${esc(profile.terms.legal_zh || '')}</textarea>
                            </div>
                            <div>
                                <label>税务说明 (EN)</label>
                                <textarea id="tax-en" rows="3">${esc(profile.terms.tax_note_en || '')}</textarea>
                            </div>
                            <div>
                                <label>税务说明 (ZH)</label>
                                <textarea id="tax-zh" rows="3">${esc(profile.terms.tax_note_zh || '')}</textarea>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px;">
                            <div>
                                <label>报价有效期 (天)</label>
                                <input type="number" id="validity-days" value="${profile.rules.quote_validity_days || 30}">
                            </div>
                            <div>
                                <label>紧急截止期 (天)</label>
                                <input type="number" id="urgent-days" value="${profile.rules.urgent_deadline_days || 7}">
                            </div>
                            <div>
                                <label>电汇阈值 (USD)</label>
                                <input type="text" id="wire-threshold" value="${profile.rules.wire_threshold_usd || '5000'}">
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 16px;">
                            <div>
                                <label>最大额外折扣 (%)</label>
                                <input type="text" id="max-discount" value="${profile.rules.max_extra_discount_pct || '10'}">
                            </div>
                            <div>
                                <label>报价前缀</label>
                                <input type="text" id="quote-prefix" value="${profile.rules.quote_prefix || 'QP-'}">
                            </div>
                        </div>
                        <small style="color: var(--muted); display: block; margin-top: 10px;">法律条款不会被 AI 导入覆盖 Legal terms are never AI-overwritten.</small>
                    </div>
                `;
                
                // Build catalog card
                let catalogRows = '';
                if (profile.catalog && Array.isArray(profile.catalog)) {
                    for (let i = 0; i < profile.catalog.length; i++) {
                        const item = profile.catalog[i];
                        const discountsStr = serializeDiscounts(item.volume_discounts || []);
                        catalogRows += `
                            <tr>
                                <td><input type="text" value="${esc(item.sku)}" data-field="sku" data-index="${i}"></td>
                                <td><input type="text" value="${esc(item.name_en)}" data-field="name_en" data-index="${i}"></td>
                                <td><input type="text" value="${esc(item.name_zh)}" data-field="name_zh" data-index="${i}"></td>
                                <td><input type="text" value="${esc(item.unit)}" data-field="unit" data-index="${i}"></td>
                                <td><input type="text" value="${esc(item.unit_zh)}" data-field="unit_zh" data-index="${i}"></td>
                                <td><input type="text" value="${item.unit_price_usd}" data-field="unit_price_usd" data-index="${i}"></td>
                                <td><input type="text" value="${esc(discountsStr)}" data-field="discounts" data-index="${i}"></td>
                                <td><button class="delete-btn" data-index="${i}">删除</button></td>
                            </tr>
                        `;
                    }
                }
                
                let catalogCard = `
                    <div class="card">
                        <h2 class="card-title">产品目录 Catalog</h2>
                        <table class="catalog-table">
                            <thead>
                                <tr>
                                    <th>SKU</th>
                                    <th>名称 (EN)</th>
                                    <th>名称 (ZH)</th>
                                    <th>单位</th>
                                    <th>单位 (ZH)</th>
                                    <th>单价 (USD)</th>
                                    <th>折扣</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="catalog-tbody">
                                ${catalogRows}
                            </tbody>
                        </table>
                        <button class="add-product-btn" id="add-product-btn">＋ 添加产品 Add product</button>
                    </div>
                `;
                
                container.innerHTML = importCard + companyCard + termsCard + catalogCard;
                
                // Setup event listeners for import
                document.getElementById('import-btn').addEventListener('click', async () => {
                    const urlInput = document.getElementById('import-url');
                    const statusDiv = document.getElementById('import-status');
                    const url = urlInput.value.trim();
                    
                    if (!url) {
                        statusDiv.innerHTML = '<div class="error-message">请输入有效的 URL</div>';
                        return;
                    }
                    
                    statusDiv.innerHTML = '<div class="warning-banner">Qwen 正在阅读网站…</div>';
                    
                    try {
                        const response = await fetchWithTimeout(`${API}/api/profile/import`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ url: url })
                        });
                        
                        if (!response.ok) {
                            const errorText = await response.text();
                            statusDiv.innerHTML = `<div class="error-message">导入失败: ${esc(errorText)}</div>`;
                            return;
                        }
                        
                        const result = await response.json();
                        
                        // Update company info
                        document.getElementById('name-en').value = result.draft.seller.name_en || '';
                        document.getElementById('name-zh').value = result.draft.seller.name_zh || '';
                        document.getElementById('jurisdiction-en').value = result.draft.seller.jurisdiction_en || '';
                        document.getElementById('jurisdiction-zh').value = result.draft.seller.jurisdiction_zh || '';
                        document.getElementById('website').value = result.draft.seller.website || '';
                        document.getElementById('email').value = result.draft.seller.email || '';
                        document.getElementById('description').value = result.draft.seller.description || '';
                        
                        // Update catalog
                        const tbody = document.getElementById('catalog-tbody');
                        tbody.innerHTML = '';
                        if (result.draft.catalog && Array.isArray(result.draft.catalog)) {
                            for (let i = 0; i < result.draft.catalog.length; i++) {
                                const item = result.draft.catalog[i];
                                const discountsStr = serializeDiscounts(item.volume_discounts || []);
                                const newRow = document.createElement('tr');
                                newRow.innerHTML = `
                                    <td><input type="text" value="${esc(item.sku)}" data-field="sku" data-index="${i}"></td>
                                    <td><input type="text" value="${esc(item.name_en)}" data-field="name_en" data-index="${i}"></td>
                                    <td><input type="text" value="${esc(item.name_zh)}" data-field="name_zh" data-index="${i}"></td>
                                    <td><input type="text" value="${esc(item.unit)}" data-field="unit" data-index="${i}"></td>
                                    <td><input type="text" value="${esc(item.unit_zh)}" data-field="unit_zh" data-index="${i}"></td>
                                    <td><input type="text" value="${item.unit_price_usd}" data-field="unit_price_usd" data-index="${i}"></td>
                                    <td><input type="text" value="${esc(discountsStr)}" data-field="discounts" data-index="${i}"></td>
                                    <td><button class="delete-btn" data-index="${i}">删除</button></td>
                                `;
                                tbody.appendChild(newRow);
                            }
                        }
                        
                        // Show note
                        statusDiv.innerHTML = `<div class="success-message">${esc(result.note)}</div>`;
                        
                        // Show warnings if needed
                        if (result.needs_price && result.needs_price.length > 0) {
                            const warningItems = result.needs_price.map(item => esc(item)).join(', ');
                            statusDiv.innerHTML += `<div class="warning-banner">以下项目需要设置价格: ${warningItems}</div>`;
                        }
                    } catch (error) {
                        statusDiv.innerHTML = `<div class="error-message">导入失败: ${esc(error.message)}</div>`;
                    }
                });
                
                // Setup event listeners for catalog
                document.getElementById('add-product-btn').addEventListener('click', () => {
                    const tbody = document.getElementById('catalog-tbody');
                    const index = tbody.children.length;
                    const newRow = document.createElement('tr');
                    newRow.innerHTML = `
                        <td><input type="text" data-field="sku" data-index="${index}"></td>
                        <td><input type="text" data-field="name_en" data-index="${index}"></td>
                        <td><input type="text" data-field="name_zh" data-index="${index}"></td>
                        <td><input type="text" data-field="unit" data-index="${index}"></td>
                        <td><input type="text" data-field="unit_zh" data-index="${index}"></td>
                        <td><input type="text" data-field="unit_price_usd" data-index="${index}"></td>
                        <td><input type="text" data-field="discounts" data-index="${index}"></td>
                        <td><button class="delete-btn" data-index="${index}">删除</button></td>
                    `;
                    tbody.appendChild(newRow);
                    
                    // Update indices for all rows
                    updateCatalogIndices();
                });
                
                // Use event delegation for delete buttons
                document.getElementById('catalog-tbody').addEventListener('click', (e) => {
                    if (e.target.classList.contains('delete-btn')) {
                        const index = parseInt(e.target.getAttribute('data-index'));
                        const rows = document.querySelectorAll('#catalog-tbody tr');
                        rows[index].remove();
                        
                        // Update indices for remaining rows
                        updateCatalogIndices();
                    }
                });
                
                // Setup save button
                const saveBar = document.createElement('div');
                saveBar.className = 'sticky-bottom-bar';
                saveBar.innerHTML = `
                    <button class="btn" id="save-settings-btn">保存配置 Save Settings</button>
                    <div class="demo-note">演示环境:配置保存在当前服务实例,实例回收后恢复默认档案。Demo: settings persist on the warm instance only.</div>
                `;
                container.appendChild(saveBar);
                
                document.getElementById('save-settings-btn').addEventListener('click', async () => {
                    // Build profile object from form values
                    const profileToSave = {
                        seller: {
                            name_en: document.getElementById('name-en').value,
                            name_zh: document.getElementById('name-zh').value,
                            jurisdiction_en: document.getElementById('jurisdiction-en').value,
                            jurisdiction_zh: document.getElementById('jurisdiction-zh').value,
                            website: document.getElementById('website').value,
                            email: document.getElementById('email').value,
                            description: document.getElementById('description').value
                        },
                        terms: {
                            payment_en: document.getElementById('payment-en').value,
                            payment_zh: document.getElementById('payment-zh').value,
                            legal_en: document.getElementById('legal-en').value,
                            legal_zh: document.getElementById('legal-zh').value,
                            tax_note_en: document.getElementById('tax-en').value,
                            tax_note_zh: document.getElementById('tax-zh').value
                        },
                        rules: {
                            quote_validity_days: parseInt(document.getElementById('validity-days').value),
                            urgent_deadline_days: parseInt(document.getElementById('urgent-days').value),
                            wire_threshold_usd: document.getElementById('wire-threshold').value,
                            max_extra_discount_pct: document.getElementById('max-discount').value,
                            quote_prefix: document.getElementById('quote-prefix').value
                        },
                        catalog: []
                    };
                    
                    // Get catalog items
                    const rows = document.querySelectorAll('#catalog-tbody tr');
                    for (let i = 0; i < rows.length; i++) {
                        const inputs = rows[i].querySelectorAll('input');
                        const item = {
                            sku: inputs[0].value,
                            name_en: inputs[1].value,
                            name_zh: inputs[2].value,
                            unit: inputs[3].value,
                            unit_zh: inputs[4].value,
                            unit_price_usd: parseFloat(inputs[5].value),
                            volume_discounts: parseDiscounts(inputs[6].value)
                        };
                        
                        // Preserve description fields if they exist in original data
                        if (profile.catalog && profile.catalog[i]) {
                            item.description_en = profile.catalog[i].description_en || '';
                            item.description_zh = profile.catalog[i].description_zh || '';
                        } else {
                            item.description_en = '';
                            item.description_zh = '';
                        }
                        
                        profileToSave.catalog.push(item);
                    }
                    
                    try {
                        const response = await fetchWithTimeout(`${API}/api/profile`, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(profileToSave)
                        });
                        
                        if (!response.ok) {
                            const errorText = await response.text();
                            document.getElementById('import-status').innerHTML = `<div class="error-message">保存失败: ${esc(errorText)}</div>`;
                            return;
                        }
                        
                        document.getElementById('import-status').innerHTML = '<div class="success-message">已保存 Saved ✓</div>';
                    } catch (error) {
                        document.getElementById('import-status').innerHTML = `<div class="error-message">保存失败: ${esc(error.message)}</div>`;
                    }
                });
                
            } catch (error) {
                container.innerHTML = `
                    <div class="warning-banner">
                        <span>API 连接失败,请稍后重试 (cold start may take ~5s)</span>
                        <button class="btn" onclick="renderSettings()">重试 Retry</button>
                    </div>
                `;
            }
        }
        
        // Update indices for catalog table rows
        function updateCatalogIndices() {
            const rows = document.querySelectorAll('#catalog-tbody tr');
            for (let i = 0; i < rows.length; i++) {
                const inputs = rows[i].querySelectorAll('input');
                inputs.forEach(input => {
                    input.setAttribute('data-index', i);
                });
                const deleteBtn = rows[i].querySelector('.delete-btn');
                deleteBtn.setAttribute('data-index', i);
            }
        }
        
        // Dashboard view
        async function renderDashboard() {
            currentRoute = 'dashboard';
            const container = document.getElementById('main-container');
            
            // Show loading state with backoff
            container.innerHTML = `
                <div class="card">
                    <h2 class="card-title">服务冷启动中,请稍候… cold start…</h2>
                </div>
            `;
            
            // Try up to 3 times with backoff
            const delays = [2000, 5000, 10000];
            let lastError = null;
            
            for (let i = 0; i < delays.length; i++) {
                try {
                    const response = await fetchWithTimeout(`${API}/api/bootstrap`);
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    
                    const data = await response.json();
                    renderDashboardWithData(container, data);
                    return;
                } catch (error) {
                    lastError = error;
                    if (i < delays.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, delays[i]));
                    }
                }
            }
            
            // If all retries failed
            container.innerHTML = `
                <div class="warning-banner">
                    <span>API 连接失败,请稍后重试 (cold start may take ~5s)</span>
                    <button class="btn" onclick="renderDashboard()">重试 Retry</button>
                </div>
            `;
        }
        
        function renderDashboardWithData(container, data) {
            let inboxCard = `
                <div class="card">
                    <h2 class="card-title">收件箱 Inbox</h2>
                    <div style="margin-bottom: 16px;">
                        <label>Sample emails:</label><br>
            `;
            
            for (const sampleName of data.samples) {
                inboxCard += `<button class="btn" onclick="loadSample('${esc(sampleName)}')" style="margin-right: 8px; margin-bottom: 8px;">${esc(sampleName)}</button>`;
            }
            
            inboxCard += `
                    </div>
                    <textarea id="email-textarea" rows="10" placeholder="Paste email text here or load a sample"></textarea>
                    <button class="btn" onclick="submitEmail()" style="margin-top: 10px;">启动自动报价 Run Autopilot</button>
                    <div id="submit-error" class="error-message"></div>
                </div>
            `;
            
            let activeCard = `
                <div class="card">
                    <h2 class="card-title">进行中 Active</h2>
            `;
            
            if (data.submissions.length > 0) {
                activeCard += `
                    <table>
                        <thead>
                            <tr>
                                <th>SID</th>
                                <th>Company</th>
                                <th>Quote #</th>
                                <th>Total</th>
                                <th>Status</th>
                                <th>Created</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                for (const sub of data.submissions) {
                    activeCard += `
                        <tr>
                            <td><a href="#/s/${esc(sub.sid)}">${esc(sub.sid)}</a></td>
                            <td>${esc(sub.company || 'N/A')}</td>
                            <td>${esc(sub.quote_number || 'N/A')}</td>
                            <td>${formatCurrency(sub.total_usd, '$')} / ${formatCurrency(sub.total_cny, '¥')}</td>
                            <td><span class="status-badge ${getStatusClass(sub.status)}">${esc(sub.status)}</span></td>
                            <td>${formatDate(sub.created_at)}</td>
                        </tr>
                    `;
                }
                
                activeCard += `
                        </tbody>
                    </table>
                `;
            } else {
                activeCard += '<div class="empty-state">No active submissions</div>';
            }
            
            activeCard += '</div>';
            
            let archiveCard = `
                <div class="card">
                    <h2 class="card-title">历史运行 Archive</h2>
            `;
            
            if (data.archived.length > 0) {
                archiveCard += `
                    <table>
                        <thead>
                            <tr>
                                <th>Run ID</th>
                                <th>Quote #</th>
                                <th>Company</th>
                                <th>Total</th>
                                <th>Decision</th>
                                <th>Time</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                for (const run of data.archived) {
                    const hasHtml = run.artifacts.some(a => a.kind === 'quote_html');
                    const quoteAction = hasHtml 
                        ? `<button class="btn" onclick="fetchAndOpenArtifact('${esc(run.run_id)}', '${esc(run.quote_number)}.html')">报价单 Quote</button>`
                        : 'N/A';
                    
                    archiveCard += `
                        <tr>
                            <td>${esc(run.run_id)}</td>
                            <td>${esc(run.quote_number || 'N/A')}</td>
                            <td>${esc(run.company || 'N/A')}</td>
                            <td>${formatCurrency(run.total_usd, '$')} / ${formatCurrency(run.total_cny, '¥')}</td>
                            <td><span class="status-badge ${getStatusClass(run.decision || 'N/A')}">${esc(run.decision || 'N/A')}</span></td>
                            <td>${formatDate(run.created_at)}</td>
                            <td>${quoteAction}</td>
                        </tr>
                    `;
                }
                
                archiveCard += `
                        </tbody>
                    </table>
                `;
            } else {
                archiveCard += '<div class="empty-state">No archived runs</div>';
            }
            
            archiveCard += '</div>';
            
            container.innerHTML = inboxCard + activeCard + archiveCard;
            
            // Start polling for active submissions
            const pollTimer = setInterval(async () => {
                if (currentRoute !== 'dashboard') return;
                
                try {
                    const response = await fetchWithTimeout(`${API}/api/bootstrap`);
                    if (!response.ok) return;
                    
                    const newData = await response.json();
                    const activeSubs = newData.submissions.filter(s => s.status === 'running' || s.status === 'awaiting_approval');
                    
                    if (activeSubs.length > 0) {
                        // Re-render the active section
                        let activeSection = `
                            <div class="card">
                                <h2 class="card-title">进行中 Active</h2>
                                <table>
                                    <thead>
                                        <tr>
                                            <th>SID</th>
                                            <th>Company</th>
                                            <th>Quote #</th>
                                            <th>Total</th>
                                            <th>Status</th>
                                            <th>Created</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                        `;
                        
                        for (const sub of activeSubs) {
                            activeSection += `
                                <tr>
                                    <td><a href="#/s/${esc(sub.sid)}">${esc(sub.sid)}</a></td>
                                    <td>${esc(sub.company || 'N/A')}</td>
                                    <td>${esc(sub.quote_number || 'N/A')}</td>
                                    <td>${formatCurrency(sub.total_usd, '$')} / ${formatCurrency(sub.total_cny, '¥')}</td>
                                    <td><span class="status-badge ${getStatusClass(sub.status)}">${esc(sub.status)}</span></td>
                                    <td>${formatDate(sub.created_at)}</td>
                                </tr>
                            `;
                        }
                        
                        activeSection += `
                                    </tbody>
                                </table>
                            </div>
                        `;
                        
                        const activeCardElement = container.querySelector('.card:nth-child(2)');
                        if (activeCardElement) {
                            activeCardElement.outerHTML = activeSection;
                        }
                    }
                } catch (err) {
                    console.error('Polling error:', err);
                }
            }, 5000);
            
            activeTimers.push(pollTimer);
        }
        
        // Submission view
        async function renderSubmission(sid) {
            currentRoute = 'submission';
            const container = document.getElementById('main-container');
            
            try {
                const response = await fetchWithTimeout(`${API}/api/s/${sid}`);
                if (!response.ok) {
                    if (response.status === 404) {
                        container.innerHTML = `
                            <a href="#/" class="back-link">← 返回 Dashboard</a>
                            <div class="card">
                                <h2 class="card-title">会话已过期 Session Expired</h2>
                                <p>该运行的内存状态已随演示实例回收 (serverless demo)。请返回 Dashboard 重新提交。</p>
                                <p>This run's in-memory state was recycled — please submit again.</p>
                                <a href="#/" class="btn">← 返回 Dashboard</a>
                            </div>
                        `;
                        return;
                    }
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const data = await response.json();
                const s = data.s;
                
                // Stage checklist
                const stages = ['intake', 'fx', 'pricing', 'risk_rules', 'risk_llm_sweep', 'drafting'];
                const stageNames = {
                    'intake': '解析询价',
                    'fx': '实时汇率',
                    'pricing': '目录定价',
                    'risk_rules': '规则风控',
                    'risk_llm_sweep': 'AI 风控扫描',
                    'drafting': '双语起草'
                };
                
                let stageList = '<div class="card"><h2 class="card-title">处理阶段 Processing Stages</h2>';
                
                for (const stage of stages) {
                    const completed = s.stages && s.stages.includes(stage);
                    const icon = completed ? '✅' : '⏳';
                    stageList += `<div class="stage-item ${completed ? 'completed' : ''}"><span class="stage-icon">${icon}</span><span class="stage-text">${esc(stageNames[stage] || stage)}</span></div>`;
                }
                
                stageList += '</div>';
                
                let content = '';
                
                if (s.status === 'running') {
                    content = `
                        <div class="card">
                            <h2 class="card-title">自动驾驶运行中… Autopilot running…</h2>
                            <p>系统正在处理您的请求，请稍候...</p>
                        </div>
                    `;
                    
                    // Poll for state updates with resilience
                    let consecutiveFailures = 0;
                    const maxConsecutiveFailures = 20;
                    let reconnectBanner = null;
                    
                    const pollTimer = setInterval(async () => {
                        if (currentRoute !== 'submission') return;
                        
                        try {
                            const stateResponse = await fetchWithTimeout(`${API}/s/${sid}/state`);
                            if (!stateResponse.ok) {
                                throw new Error(`HTTP ${stateResponse.status}`);
                            }
                            
                            const stateData = await stateResponse.json();
                            
                            // Clear any reconnect banner on success
                            if (consecutiveFailures > 0) {
                                consecutiveFailures = 0;
                                if (reconnectBanner) {
                                    reconnectBanner.remove();
                                    reconnectBanner = null;
                                }
                            }
                            
                            // Update stage checklist based on new stages
                            const updatedStageList = '<div class="card"><h2 class="card-title">处理阶段 Processing Stages</h2>' +
                                stages.map(stage => {
                                    const completed = stateData.stages.includes(stage);
                                    const icon = completed ? '✅' : '⏳';
                                    return `<div class="stage-item ${completed ? 'completed' : ''}"><span class="stage-icon">${icon}</span><span class="stage-text">${esc(stageNames[stage] || stage)}</span></div>`;
                                }).join('') +
                                '</div>';
                            
                            const stageCard = document.querySelector('.card:first-child');
                            if (stageCard) {
                                stageCard.outerHTML = updatedStageList;
                            }
                            
                            // If status changed, reload the full view
                            if (stateData.status !== s.status) {
                                clearInterval(pollTimer);
                                renderSubmission(sid);
                            }
                        } catch (err) {
                            console.error('Polling error:', err);
                            
                            // Increment failure counter
                            consecutiveFailures++;
                            
                            // Show reconnect banner if not already shown
                            if (!reconnectBanner && consecutiveFailures <= maxConsecutiveFailures) {
                                reconnectBanner = document.createElement('div');
                                reconnectBanner.className = 'reconnect-banner';
                                reconnectBanner.textContent = '连接中断,自动重试中… reconnecting…';
                                
                                const firstCard = document.querySelector('.card');
                                if (firstCard) {
                                    firstCard.parentNode.insertBefore(reconnectBanner, firstCard);
                                }
                            }
                            
                            // Stop polling after max consecutive failures
                            if (consecutiveFailures >= maxConsecutiveFailures) {
                                clearInterval(pollTimer);
                                if (reconnectBanner) {
                                    reconnectBanner.remove();
                                }
                                const errorCard = document.createElement('div');
                                errorCard.className = 'card';
                                errorCard.innerHTML = `
                                    <h2 class="card-title">连接超时 Connection Timeout</h2>
                                    <p>无法获取最新状态，已停止轮询。请刷新页面或返回 Dashboard。</p>
                                `;
                                const container = document.getElementById('main-container');
                                container.appendChild(errorCard);
                            }
                        }
                    }, 1500);
                    
                    activeTimers.push(pollTimer);
                    
                } else if (s.status === 'awaiting_approval') {
                    let riskFlags = '';
                    if (s.risk_flags && s.risk_flags.length > 0) {
                        riskFlags = '<div class="card"><h2 class="card-title">风险标记 Risk Flags</h2>';
                        for (const flag of s.risk_flags) {
                            riskFlags += `
                                <div style="margin-bottom: 10px;">
                                    <span class="${getSeverityClass(flag.severity)}">${esc(flag.code)}</span>
                                    <span style="margin-left: 8px;">${esc(flag.message_zh)}</span>
                                    <small style="display: block; color: var(--muted);">${esc(flag.message_en)}</small>
                                </div>
                            `;
                        }
                        riskFlags += '</div>';
                    }
                    
                    let summary = '';
                    if (data.summary) {
                        summary = `<div class="card"><h2 class="card-title">摘要 Summary</h2><pre>${esc(data.summary)}</pre></div>`;
                    }
                    
                    let preview = '';
                    try {
                        const previewResponse = await fetchWithTimeout(`${API}/s/${sid}/preview`);
                        if (previewResponse.ok) {
                            const previewHtml = await previewResponse.text();
                            preview = `<div class="card"><h2 class="card-title">报价预览 Quote Preview</h2><iframe class="preview-frame" srcdoc="${esc(previewHtml)}"></iframe></div>`;
                        }
                    } catch (err) {
                        console.error('Preview fetch error:', err);
                    }
                    
                    let blockWarning = '';
                    let approveDisabled = false;
                    if (s.risk_flags && s.risk_flags.some(f => f.severity === 'block')) {
                        blockWarning = '<div class="block-warning">⛔ 存在阻断级风险,不可批准 Blocking flag — approval disabled</div>';
                        approveDisabled = true;
                    }
                    
                    content = `
                        ${riskFlags}
                        ${summary}
                        ${preview}
                        <div class="card decision-bar">
                            <h2 class="card-title">决策 Decision</h2>
                            <textarea id="decision-notes" class="notes-input" rows="3" placeholder="审批备注 Notes"></textarea>
                            <button class="btn btn-approve" ${approveDisabled ? 'disabled' : ''} onclick="makeDecision('${esc(sid)}', 'approve')">批准并生成 Approve & Render</button>
                            <button class="btn btn-reject" onclick="makeDecision('${esc(sid)}', 'reject')">拒绝 Reject</button>
                            <div id="decision-error" class="error-message"></div>
                            ${blockWarning}
                        </div>
                    `;
                    
                } else if (s.status === 'approved' || s.status === 'rejected') {
                    let artifacts = '';
                    if (s.artifacts && s.artifacts.length > 0) {
                        artifacts = '<div class="artifact-list"><h3>交付物 Artifacts</h3>';
                        for (const artifact of s.artifacts) {
                            let label = artifact.kind;
                            switch (artifact.kind) {
                                case 'quote_html':
                                    label = '报价单 Quote HTML';
                                    break;
                                case 'reply_email':
                                    label = '回复邮件 Reply Email';
                                    break;
                                case 'quote_json':
                                    label = 'Quote JSON';
                                    break;
                                case 'inquiry':
                                    label = 'Inquiry JSON';
                                    break;
                                case 'summary':
                                    label = 'Summary';
                                    break;
                            }
                            artifacts += `<button class="artifact-btn" onclick="fetchAndOpenArtifact('${esc(artifact.run_id)}', '${esc(artifact.filename)}')">${esc(label)}</button>`;
                        }
                        artifacts += '</div>';
                    }
                    
                    content = `
                        <div class="card">
                            <h2 class="card-title">结果 Result</h2>
                            <p>状态 Status: <span class="status-badge ${getStatusClass(s.status)}">${esc(s.status)}</span></p>
                            ${artifacts}
                            ${s.tokens ? `<div class="tokens-info">本次运行消耗 ${s.tokens} tokens</div>` : ''}
                        </div>
                    `;
                    
                } else if (s.status === 'failed') {
                    content = `
                        <div class="card">
                            <h2 class="card-title">错误 Error</h2>
                            <div style="background-color: #fee2e2; padding: 16px; border-radius: 6px; color: #b91c1c;">
                                ${esc(s.error)}
                            </div>
                        </div>
                    `;
                }
                
                container.innerHTML = `
                    <a href="#/" class="back-link">← 返回 Dashboard</a>
                    ${stageList}
                    ${content}
                `;
                
            } catch (error) {
                container.innerHTML = `
                    <a href="#/" class="back-link">← 返回 Dashboard</a>
                    <div class="warning-banner">
                        <span>API 连接失败,请稍后重试 (cold start may take ~5s)</span>
                        <button class="btn" onclick="renderSubmission('${esc(sid)}')">重试 Retry</button>
                    </div>
                `;
            }
        }
        
        // Event handlers
        async function loadSample(name) {
            try {
                const response = await fetchWithTimeout(`${API}/sample/${encodeURIComponent(name)}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const data = await response.json();
                document.getElementById('email-textarea').value = data.text;
            } catch (error) {
                console.error('Error loading sample:', error);
                document.getElementById('submit-error').textContent = 'Failed to load sample';
            }
        }
        
        async function submitEmail() {
            const textarea = document.getElementById('email-textarea');
            const errorDiv = document.getElementById('submit-error');
            
            if (!textarea.value.trim()) {
                errorDiv.textContent = 'Please enter email text';
                return;
            }
            
            try {
                const response = await fetchWithTimeout(`${API}/api/submit`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ email_text: textarea.value })
                });
                
                if (response.status === 422) {
                    errorDiv.textContent = 'Email text too short';
                    return;
                }
                
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const data = await response.json();
                window.location.hash = `#/s/${data.sid}`;
            } catch (error) {
                console.error('Submit error:', error);
                errorDiv.textContent = 'Failed to submit email';
            }
        }
        
        async function makeDecision(sid, action) {
            const notesInput = document.getElementById('decision-notes');
            const errorDiv = document.getElementById('decision-error');
            
            try {
                const response = await fetchWithTimeout(`${API}/api/s/${sid}/decision`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        action: action,
                        notes: notesInput.value.trim() || null
                    })
                });
                
                if (response.status === 409) {
                    errorDiv.textContent = 'Conflict - already decided';
                    return;
                }
                
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                // Reload the submission view
                renderSubmission(sid);
            } catch (error) {
                console.error('Decision error:', error);
                errorDiv.textContent = 'Failed to make decision';
            }
        }
        
        async function fetchAndOpenArtifact(runId, filename) {
            try {
                const response = await fetchWithTimeout(`${API}/artifacts/${encodeURIComponent(runId)}/${encodeURIComponent(filename)}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                window.open(url, '_blank');
                
                // Clean up the URL after some time
                setTimeout(() => URL.revokeObjectURL(url), 10000);
            } catch (error) {
                console.error('Artifact fetch error:', error);
                alert('Failed to fetch artifact');
            }
        }
        
        // Initialize
        window.addEventListener('hashchange', handleHashChange);
        handleHashChange(); // Initial render
    </script>
</body>
</html>

```

## Output
One file: `docs/index.html`, complete.
