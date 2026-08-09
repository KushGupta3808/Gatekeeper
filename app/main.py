"""
GateKeeper - Stage 3: Gateway with swappable rate-limiting algorithm.

Run with:
    uvicorn app.main:app --reload --port 8000

Swap the algorithm via env var (default: token_bucket):
    RATE_LIMIT_ALGORITHM=sliding_window_log uvicorn app.main:app --port 8000
    RATE_LIMIT_ALGORITHM=sliding_window_counter uvicorn app.main:app --port 8000

Test with:
    curl "http://localhost:8000/api/data?client_id=kush"
"""

from fastapi import FastAPI, HTTPException, Query

from app.config import build_limiter, ALGORITHM

app = FastAPI(title=f"GateKeeper - Stage 3 ({ALGORITHM})")

limiter = build_limiter()


@app.get("/api/data")
def get_data(client_id: str = Query(..., description="Simulates an API key")):
    """
    A stand-in for 'the real backend endpoint' this gateway would protect.
    In later stages this becomes an actual proxy to a separate service.
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
