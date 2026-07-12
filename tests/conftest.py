import pytest

# A test-only admin password. NOT the production credential — the real admin
# password is injected via QP_ADMIN_PASSWORD (never committed). Tests force this
# value so no real password ever appears in the repo.
ADMIN_TEST_PASSWORD = "admin-test-pw-9x"


@pytest.fixture(autouse=True)
def _isolate_auth_store(tmp_path_factory, monkeypatch):
    """Point the user store at a fresh temp file and pin a known admin password
    so tests never read/write the real local store or embed a real credential."""
    from quotepilot.web import auth

    store = tmp_path_factory.mktemp("auth") / "users.json"
    monkeypatch.setenv("QP_USER_STORE", str(store))
    monkeypatch.setattr(auth, "ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    with auth._lock:
        auth._SESSIONS.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_guard_state():
    """Clear per-IP rate-limit and daily-cap counters between tests so they
    don't interfere with each other (all tests share one client IP)."""
    from quotepilot.web import guard

    with guard._lock:
        guard._ip_hits.clear()
        guard._daily.update(submit=0, **{"import": 0})
    yield
