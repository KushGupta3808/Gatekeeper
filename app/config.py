"""
GateKeeper - Algorithm configuration

Lets us swap which rate-limiting algorithm the gateway uses via a single
environment variable, without touching main.py's logic. This is what
makes it possible to say "here are the tradeoffs, and here's how you'd
switch between them in production" rather than just having built one.
"""

import os
import redis

from app.rate_limiter_redis import RedisRateLimiter
from app.rate_limiter_sliding_log import SlidingWindowLogLimiter
from app.rate_limiter_sliding_counter import SlidingWindowCounterLimiter

ALGORITHM = os.environ.get("RATE_LIMIT_ALGORITHM", "token_bucket")

redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)


def build_limiter():
    if ALGORITHM == "token_bucket":
        # allows bursts up to `capacity`, refills over time
        return RedisRateLimiter(redis_client, capacity=5, refill_rate=1.0)

    elif ALGORITHM == "sliding_window_log":
        # perfectly accurate, memory grows with request volume
        return SlidingWindowLogLimiter(redis_client, limit=5, window_seconds=5.0)

    elif ALGORITHM == "sliding_window_counter":
        # near-accurate approximation, O(1) memory per client
        return SlidingWindowCounterLimiter(redis_client, limit=5, window_seconds=5.0)

    else:
        raise ValueError(f"Unknown RATE_LIMIT_ALGORITHM: {ALGORITHM}")
