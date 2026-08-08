"""
GateKeeper - Naive Token Bucket Rate Limiter (Stage 1)

This is intentionally the "wrong" version for a multi-instance deployment.
It works perfectly on a single process. We're building it first so the
distributed-state problem (see TRD Section 2) is something you SEE break,
not just something you're told about.
"""

import time


class TokenBucket:
    """
    One bucket = one client's rate limit state.

    capacity      -> max tokens the bucket can hold (max burst size)
    refill_rate   -> tokens added per second
    tokens        -> current tokens available right now
    last_refill   -> timestamp of the last time we topped up the bucket
    """

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity          # start full
        self.last_refill = time.monotonic()

    def _refill(self):
        """
        Lazy refill: instead of running a background timer, we calculate
        how many tokens SHOULD have been added since we last checked,
        based on elapsed time. This is the standard trick - no scheduler
        needed, just math at read time.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate

        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def allow_request(self) -> bool:
        """Try to spend 1 token. Returns True if allowed, False if rejected."""
        self._refill()

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class NaiveRateLimiter:
    """
    Holds one TokenBucket per client_id, all in a plain Python dict
    living in THIS PROCESS's memory.

    THE PROBLEM (see TRD Section 2):
    If you run two instances of this app (e.g. `uvicorn` on port 8000
    AND port 8001, both behind a load balancer), each instance gets its
    own separate `self.buckets` dict. A client bouncing between the two
    instances effectively gets 2x the intended limit, because neither
    instance knows what the other has already counted.

    We'll fix this in Stage 2 by moving `tokens` and `last_refill` into
    Redis, so every instance reads/writes the SAME state.
    """

    def __init__(self, capacity: int = 10, refill_rate: float = 2.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.buckets: dict[str, TokenBucket] = {}

    def is_allowed(self, client_id: str) -> bool:
        if client_id not in self.buckets:
            self.buckets[client_id] = TokenBucket(self.capacity, self.refill_rate)

        return self.buckets[client_id].allow_request()
