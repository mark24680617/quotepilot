"""Live USD/CNY rate with keyless public APIs and an offline fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

from .. import config
from ..models import FxRate

def _er_api_rate(d: dict) -> float:
    if d.get("result") != "success":
        raise ValueError("er-api returned non-success result")
    return d["rates"]["CNY"]  # CNY = onshore rate (not CNH)


_SOURCES = [
    # (name, url, path to rate as a callable)
    ("open.er-api.com", "https://open.er-api.com/v6/latest/USD", _er_api_rate),
    (
        "frankfurter.dev",
        "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CNY",
        lambda d: d["rates"]["CNY"],
    ),
]


def get_usd_cny(timeout: float = 10.0) -> FxRate:
    for name, url, pick in _SOURCES:
        try:
            resp = httpx.get(url, timeout=timeout)
            resp.raise_for_status()
            rate = Decimal(str(pick(resp.json())))
            return FxRate(
                rate=rate,
                source=name,
                as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        except Exception:
            continue
    return FxRate(
        rate=config.FALLBACK_USD_CNY,
        source="offline-fallback (indicative)",
        as_of=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        offline=True,
    )
