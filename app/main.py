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
from app.config import build_limiter, ALGORITHM

app = FastAPI(title=f"GateKeeper - Stage 4 ({ALGORITHM}, JWT auth)")

limiter = build_limiter()


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
    Protected endpoint. client_id no longer comes from a query param
    anyone could fake - it comes from inside a verified JWT, so a
    client can't dodge their own rate limit by claiming a different
    identity in the URL.
    """
    if not limiter.is_allowed(client_id):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Slow down.",
        )

    return {"client_id": client_id, "message": "request allowed", "data": "here's your data"}


@app.get("/health")
def health():
    return {"status": "ok"}