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

from fastapi import Depends, FastAPI, HTTPException, Query

from app.auth import create_token, get_client_id_from_header
from app.backend_client import call_backend, set_backend_healthy
from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.config import build_limiter, ALGORITHM

app = FastAPI(title=f"GateKeeper - Stage 5 ({ALGORITHM}, JWT auth, circuit breaker)")

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
    Now also routes the actual backend call through the circuit
    breaker (Stage 5): if the backend has been failing, requests get
    rejected instantly with 503 instead of hanging on a doomed call.
    """
    if not limiter.is_allowed(client_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down.",
        )

    try:
        result = breaker.call(call_backend, client_id)
    except CircuitBreakerOpenError:
        raise HTTPException(
            status_code=503,
            detail="Backend unavailable (circuit breaker open) - not even attempting the call.",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Backend call failed")

    return {**result, "message": "request allowed"}


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