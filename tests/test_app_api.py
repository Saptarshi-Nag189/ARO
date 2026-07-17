"""Flask API surface: validation, auth plumbing, eviction, path safety."""

import time

import pytest

import app as aro_app


@pytest.fixture
def client():
    return aro_app.app.test_client()


# ─── Input validation (finding 2.15) ─────────────────────────────────────


def test_run_requires_json(client):
    r = client.post("/api/run", data="objective=x")
    assert r.status_code in (400, 415)


def test_run_requires_objective(client):
    r = client.post("/api/run", json={"objective": "   "})
    assert r.status_code == 400


def test_run_rejects_unknown_mode(client):
    r = client.post("/api/run", json={"objective": "x", "mode": "bananas"})
    assert r.status_code == 400
    assert "invalid mode" in r.get_json()["error"]


def test_run_rejects_unknown_runtime_mode(client):
    r = client.post("/api/run", json={"objective": "x", "runtime_mode": "debug"})
    assert r.status_code == 400
    assert "runtime_mode" in r.get_json()["error"]


# ─── Session ID validation / path traversal (SEC-003) ────────────────────


@pytest.mark.parametrize("bad_id", [
    "..%2F..%2Fetc", "session_XYZ", "session_..%2F..", "notasession",
])
def test_report_rejects_malformed_session_ids(client, bad_id):
    r = client.get(f"/api/report/{bad_id}")
    assert r.status_code in (400, 404)


def test_stream_rejects_malformed_session_ids(client):
    r = client.get("/api/stream/not_a_session")
    assert r.status_code == 400


def test_report_missing_session_is_404(client):
    r = client.get("/api/report/session_aaaaaaaaaaaa")
    assert r.status_code == 404


# ─── Session eviction (finding 2.6) ──────────────────────────────────────


def test_completed_sessions_are_evicted():
    aro_app._session_status["session_evictme12345"] = {
        "status": "complete", "completed_at": time.time() - 7200,
    }
    aro_app._session_status["session_running12345"] = {"status": "running"}
    try:
        aro_app._evict_old_sessions()
        assert "session_evictme12345" not in aro_app._session_status
        assert "session_running12345" in aro_app._session_status
    finally:
        aro_app._session_status.pop("session_running12345", None)


# ─── Health & headers ────────────────────────────────────────────────────


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert "active_sessions" in body


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"


# ─── API key auth incl. SSE query param (finding 2.13) ───────────────────


def test_api_key_enforcement_and_query_param_fallback(client, monkeypatch):
    monkeypatch.setattr(aro_app, "_ARO_API_KEY", "sekrit")

    # No key → 401
    assert client.get("/api/sessions").status_code == 401
    # Wrong key → 401
    assert client.get(
        "/api/sessions", headers={"X-API-Key": "wrong"}).status_code == 401
    # Header key → allowed
    assert client.get(
        "/api/sessions", headers={"X-API-Key": "sekrit"}).status_code == 200
    # Query-param key (EventSource path) → allowed past auth
    r = client.get("/api/stream/session_aaaaaaaaaaaa?api_key=sekrit")
    assert r.status_code == 404  # authorized, but session doesn't exist
    # Health stays open for load balancers
    assert client.get("/api/health").status_code == 200


# ─── Rate limiting on /api/run ───────────────────────────────────────────


def test_run_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(aro_app, "RATE_LIMIT_MAX_RUNS", 1)
    monkeypatch.setattr(aro_app, "_run_request_times", {})

    # First request consumes the allowance (fails validation, but counts)
    r1 = client.post("/api/run", json={"objective": ""})
    assert r1.status_code == 400
    # Second request inside the window is rejected
    r2 = client.post("/api/run", json={"objective": ""})
    assert r2.status_code == 429
    assert "rate limit" in r2.get_json()["error"]
