"""
GateKeeper - Stage 4: Gateway with JWT auth + swappable rate-limiting.

Run with:
    uvicorn app.main:app --reload --port 8000

Swap the rate-limit algorithm via env var (default: token_bucket):
    RATE_LIMIT_ALGORITHM=sliding_window_log uvicorn app.main:app --port 8000
    RATE_LIMIT_ALGORITHM=sliding_window_counter uvicorn app.main:app --port 8000

Usage:
    1. Get a token (stands in for a real login flow):
       curl "http://localhost:8000/auth/token?client_id=kush"

    2. Use it to call the protected endpoint:
       curl http://localhost:8000/api/data \\
            -H "Authorization: Bearer <token from step 1>"
"""

import time

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.auth import create_token, get_client_id_from_header
from app.backend_client import call_backend, set_backend_healthy
from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.config import build_limiter, ALGORITHM
from app.metrics import circuit_breaker_open, request_duration_seconds, requests_total

app = FastAPI(title=f"GateKeeper - Stage 6 ({ALGORITHM}, JWT auth, circuit breaker, metrics)")

limiter = build_limiter()
breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)


@app.get("/auth/token")
def issue_token(client_id: str = Query(..., description="Who this token identifies")):
    """
    Stand-in for a real login/API-key exchange. In production this
    would sit behind actual credential verification - here it just
    issues a signed token for whatever client_id is requested, so we
    can demo the flow end-to-end.
    """
    token = create_token(client_id)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/data")
def get_data(client_id: str = Depends(get_client_id_from_header)):
    """
    Protected endpoint. client_id comes from a verified JWT (Stage 4).
    Backend call routed through the circuit breaker (Stage 5).
    Now also instrumented (Stage 6): every outcome increments a
    labeled counter, every call's duration feeds the latency
    histogram, and the breaker's open/closed state updates a gauge.
    """
    start_time = time.monotonic()

    if not limiter.is_allowed(client_id):
        requests_total.labels(outcome="rate_limited").inc()
        request_duration_seconds.observe(time.monotonic() - start_time)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down.",
        )

    try:
        result = breaker.call(call_backend, client_id)
    except CircuitBreakerOpenError:
        circuit_breaker_open.set(1)
        requests_total.labels(outcome="circuit_open").inc()
        request_duration_seconds.observe(time.monotonic() - start_time)
        raise HTTPException(
            status_code=503,
            detail="Backend unavailable (circuit breaker open) - not even attempting the call.",
        )
    except Exception:
        circuit_breaker_open.set(1 if breaker.state.value == "open" else 0)
        requests_total.labels(outcome="backend_error").inc()
        request_duration_seconds.observe(time.monotonic() - start_time)
        raise HTTPException(status_code=502, detail="Backend call failed")

    circuit_breaker_open.set(0)
    requests_total.labels(outcome="allowed").inc()
    request_duration_seconds.observe(time.monotonic() - start_time)
    return {**result, "message": "request allowed"}


@app.get("/metrics")
def metrics():
    """
    The endpoint Prometheus will periodically 'pull' from. Returns all
    current metric values in Prometheus's plain-text exposition format.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/admin/backend/{status}")
def toggle_backend(status: str):
    """
    Demo-only endpoint: flips the simulated backend healthy/unhealthy
    so you can watch the circuit breaker react through real requests.
    Not something a real gateway would expose publicly.
    """
    if status not in ("healthy", "broken"):
        raise HTTPException(status_code=400, detail="status must be 'healthy' or 'broken'")

    set_backend_healthy(status == "healthy")
    return {"backend_status": status}


@app.get("/admin/breaker-state")
def breaker_state():
    """Demo-only: peek at the breaker's current state."""
    return {"state": breaker.state.value, "failure_count": breaker.failure_count}


@app.get("/health")
def health():
    return {"status": "ok"}
