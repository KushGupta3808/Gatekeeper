"""
GateKeeper - Stage 1: Single-process gateway with naive rate limiting.

Run with:
    uvicorn app.main:app --reload --port 8000

Test with:
    curl "http://localhost:8000/api/data?client_id=kush"
"""

from fastapi import FastAPI, HTTPException, Query

from app.rate_limiter_naive import NaiveRateLimiter

app = FastAPI(title="GateKeeper - Stage 1 (Naive)")

# One shared limiter instance for this process.
# capacity=5, refill_rate=1 -> allows a burst of 5, then 1 request/sec after.
limiter = NaiveRateLimiter(capacity=5, refill_rate=1.0)


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
