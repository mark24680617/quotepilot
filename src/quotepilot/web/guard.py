"""Abuse guards for the public demo backend: per-IP rate limits, a global
daily circuit-breaker, input caps, and security headers.

None of this is real authentication (the frontend is open source). It exists to
make casual/drive-by abuse of the anonymous, credit-spending API expensive and
bounded. The real backstop is an Alibaba Cloud spend cap on the account.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import HTTPException, Request

# (Profile writes are now protected by real per-user auth in auth.py; the old
# shared write-token deterrent was removed when login was added.)

# --- input caps ---
MAX_EMAIL_CHARS = 20_000
MAX_PROFILE_BYTES = 200_000
MAX_LINE_ITEMS = 100
MAX_SUBMISSIONS = 200  # evict oldest beyond this
MAX_INFLIGHT = 8       # concurrent pipelines (bounded worker pool)

# --- rate limits: (max events, window seconds) per client IP ---
LIMITS = {
    "submit": (8, 3600),          # 8 autopilot runs / hour / IP
    "import": (5, 3600),          # 5 website imports / hour / IP
    "profile_write": (20, 3600),  # 20 profile saves / hour / IP
    "auth": (40, 3600),           # login/signup attempts / hour / IP (brute-force brake)
    "decision": (60, 3600),
}

# --- global daily circuit breaker (per instance) ---
DAILY_RUN_CAP = 300      # total /api/submit across all IPs per day per instance
DAILY_IMPORT_CAP = 150

_lock = threading.Lock()
_ip_hits: dict[str, deque[float]] = defaultdict(deque)
_daily = {"day": date.today().isoformat(), "submit": 0, "import": 0}


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, bucket: str) -> None:
    """Raise 429 if the client IP exceeds the bucket's limit."""
    max_events, window = LIMITS.get(bucket, (30, 3600))
    ip = client_ip(request)
    key = f"{bucket}:{ip}"
    now = time.time()
    with _lock:
        dq = _ip_hits[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= max_events:
            retry = int(dq[0] + window - now) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit: max {max_events} per {window // 60} min. Retry in ~{retry}s.",
                headers={"Retry-After": str(retry)},
            )
        dq.append(now)
        # opportunistic cleanup so the map can't grow unbounded
        if len(_ip_hits) > 5000:
            for k in [k for k, v in list(_ip_hits.items()) if not v or v[-1] < now - window]:
                _ip_hits.pop(k, None)


def daily_gate(kind: str) -> None:
    """Global per-instance daily cap — the circuit breaker for the credit."""
    cap = DAILY_RUN_CAP if kind == "submit" else DAILY_IMPORT_CAP
    with _lock:
        today = date.today().isoformat()
        if _daily["day"] != today:
            _daily.update(day=today, submit=0, **({"import": 0}))
        if _daily[kind] >= cap:
            raise HTTPException(
                status_code=429,
                detail="Daily demo capacity reached — this public demo caps model usage to protect the credit. Try again tomorrow, or run it locally from the repo.",
            )
        _daily[kind] += 1


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # API returns JSON/small HTML; block everything, allow nothing to run framed.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}
