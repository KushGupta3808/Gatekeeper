"""
GateKeeper - Sliding Window Log Rate Limiter (Stage 3a)

Perfectly accurate rate limiting: for each client, we keep an actual
timestamped log of every allowed request in a Redis SORTED SET (ZSET).
A ZSET stores members ranked by a numeric "score" - here we use the
request timestamp itself as both the member and the score.

To decide if a new request is allowed:
  1. Throw away any log entries older than the window (they're no
     longer relevant to "requests in the last N seconds").
  2. Count what's left.
  3. If under the limit, log this request too and allow it.

Tradeoff vs token bucket: perfectly accurate (no burst edge cases),
but memory grows with request VOLUME, not just number of clients -
a client making 1000 requests/sec needs 1000 entries stored, even
if they're all within the allowed limit.
"""

import time
import redis


SLIDING_WINDOW_LOG_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

local window_start = now - window_seconds

-- Step 1: drop any log entries older than the window. ZREMRANGEBYSCORE
-- removes every member whose score falls in the given range - here,
-- "the beginning of time" up to window_start.
redis.call("ZREMRANGEBYSCORE", key, 0, window_start)

-- Step 2: count what's left inside the window right now.
local current_count = redis.call("ZCARD", key)

local allowed = 0
if current_count < limit then
    -- Step 3: log this request (member and score are both just `now`;
    -- in the rare case two requests land at the exact same float
    -- timestamp, ZADD still stores them as distinct entries because
    -- we make the member string unique below in Python).
    redis.call("ZADD", key, now, now .. "-" .. tostring(math.random()))
    redis.call("EXPIRE", key, window_seconds + 1)
    allowed = 1
end

return allowed
"""


class SlidingWindowLogLimiter:
    def __init__(self, redis_client: redis.Redis, limit: int = 5, window_seconds: float = 5.0):
        self.redis = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self._script = self.redis.register_script(SLIDING_WINDOW_LOG_LUA)

    def is_allowed(self, client_id: str) -> bool:
        key = f"sw_log:{client_id}"
        now = time.time()

        result = self._script(
            keys=[key],
            args=[now, self.window_seconds, self.limit],
        )
        return result == 1
