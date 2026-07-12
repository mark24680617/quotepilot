# Security posture

QuotePilot is a public hackathon demo: an **anonymous** frontend on GitHub Pages
calling an **anonymous** JSON API on Alibaba Cloud Function Compute that spends a
prepaid Qwen credit. There is no user login by design. This document records the
threat model and the guards in place after a multi-agent security audit.

## What's protected

| Risk | Mitigation |
|---|---|
| **Qwen credit drain** (anonymous `/api/submit`, `/api/profile/import` call paid models) | Per-IP rate limits + a **global daily cap** (`guard.daily_gate`) that fails closed before any model call; bounded worker pool (`MAX_INFLIGHT`); input size caps (`email_text` ≤ 20k chars). The real backstop is the **prepaid, no-auto-recharge** account (see below). |
| **Demo-profile defacement** (anonymous profile writes) | A shared **write token** (`X-QP-Write-Token`, env `QP_WRITE_TOKEN`) is required by PUT `/api/profile`, POST `/api/profile/save`, and `/import`. Deterrence not auth (token ships in the open-source frontend) — stops casual drive-by defacement; backed by rate-limit + ephemeral `/tmp` storage that self-heals on instance recycle. |
| **Cross-user control** (anyone could approve/edit/reject any run) | Each run mints an **owner token** returned only to the submitting tab; edit/approve/reject require `X-QP-Owner-Token`. List endpoints never expose it. |
| **SSRF via website import** reaching cloud metadata | `_ip_blocked` rejects non-global / private / loopback / link-local / reserved / multicast **and IPv4-mapped IPv6** (`::ffff:169.254.169.254`) and the metadata IPs; redirects are re-validated per hop. Residual DNS-rebinding TOCTOU is accepted for a demo. |
| **Stored XSS via artifact/quote HTML** | Quote templates are Jinja **autoescaped**; artifacts are viewed in a **fully sandboxed iframe** (`sandbox=""`, no scripts, unique origin) — never `window.open` of a same-origin blob. Backend serves artifacts with `Content-Disposition: attachment`. |
| **Path traversal** on `/artifacts` | Regex-validated ids + a resolved-path containment check under `RUNS_DIR`. |
| **Cross-site API abuse** | App-layer CORS restricted to the Pages origin (+ localhost), `allow_credentials=False`. **Residual:** the `fcapp.run` platform gateway still reflects arbitrary `Origin` on responses — this cannot be overridden in app code (needs a custom domain / WAF). Impact is bounded because the API is anonymous with no cookies (nothing sensitive to steal cross-origin) and the per-IP + daily caps bound any drive-by credit abuse. |
| **Info disclosure** | Generic client error messages (real details logged server-side); security headers (CSP `default-src 'none'`, `frame-ancestors 'none'`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, HSTS, Referrer-Policy). |
| **DoS** (thread/memory) | Bounded worker pool; `SUBMISSIONS` map evicts oldest beyond `MAX_SUBMISSIONS`; input caps. |
| **Secret leakage** | Verified clean across full git history. `.env` git-ignored; `s.yaml` uses `${env(QWEN_API_KEY)}`; deploy AccessKey lives only in `~/.s/` (outside the repo). |

## Operator action (the real credit backstop)

App-level caps slow abuse but cannot fully stop a determined attacker rotating
IPs. Make the **$40 credit a hard ceiling**:

1. In the Alibaba Cloud billing console, ensure **no pay-as-you-go payment
   method / auto-recharge** is bound to the account running ModelStudio + FC —
   so spend stops when the credit is exhausted.
2. Set a **budget alert** at e.g. $20 / $35.
3. Rotate the `QWEN_API_KEY` after the event.

## Tunables (env vars on the function)

- `QP_ALLOWED_ORIGINS` — comma-separated CORS allowlist.
- Caps live in `src/quotepilot/web/guard.py` (`LIMITS`, `DAILY_RUN_CAP`,
  `DAILY_IMPORT_CAP`, `MAX_INFLIGHT`, `MAX_EMAIL_CHARS`).

## Reporting

Open a GitHub issue (no sensitive details) or contact the maintainer privately.
