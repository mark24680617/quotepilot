import pytest


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """Clear per-IP rate-limit and daily-cap counters between tests so they
    don't interfere with each other (all tests share one client IP)."""
    from quotepilot.web import guard

    with guard._lock:
        guard._ip_hits.clear()
        guard._daily.update(submit=0, **{"import": 0})
    yield
