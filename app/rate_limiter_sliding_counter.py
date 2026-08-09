"""
GateKeeper - Sliding Window Counter Rate Limiter (Stage 3b)

The industry-standard middle ground between token bucket and sliding
window log: near-accurate rate limiting using O(1) memory per client
(two counters), instead of the log's O(request volume) memory.

HOW IT WORKS:
Time is divided into fixed-size buckets (e.g. one bucket per second).
We only ever need to know two numbers: how many requests landed in the
CURRENT bucket, and how many landed in the PREVIOUS bucket.

To estimate "how many requests in the last N seconds, right now" we
don't recount anything - we take the current bucket's count, plus a
WEIGHTED portion of the previous bucket's count. The weight is based
on how far we are into the current bucket: if we're only 20% of the
way into the current bucket, we assume 80% of the previous bucket's
requests are still "within the last N seconds" of right now.

estimated_count = current_count + previous_count * (1 - elapsed_fraction)

This trades a small amount of accuracy (it assumes requests are evenly
spread within a bucket, which isn't exactly true) for O(1) memory,
which is why this is what most real-world gateways (Cloudflare, etc)
actually run in production.
"""

import time
import redis


SLIDING_WINDOW_COUNTER_LUA = """
local key_prefix = KEYS[1]
local now = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Which fixed-size bucket are we in right now? Integer division floors
-- this, so e.g. with a 5-second window, timestamps 100-104 are all
-- bucket 20, timestamps 105-109 are all bucket 21.
local current_bucket_id = math.floor(now / window_seconds)
local previous_bucket_id = current_bucket_id - 1

local current_key = key_prefix .. ":" .. current_bucket_id
local previous_key = key_prefix .. ":" .. previous_bucket_id

local current_count = tonumber(redis.call("GET", current_key)) or 0
local previous_count = tonumber(redis.call("GET", previous_key)) or 0

-- how far into the CURRENT bucket are we, as a fraction (0.0 to 1.0)?
local elapsed_in_bucket = now - (current_bucket_id * window_seconds)
local elapsed_fraction = elapsed_in_bucket / window_seconds

-- weight the previous bucket's count by how much of it still "counts"
-- as within the last `window_seconds` from right now
local estimated_count = current_count + previous_count * (1 - elapsed_fraction)

local allowed = 0
if estimated_count < limit then
    redis.call("INCR", current_key)
    redis.call("EXPIRE", current_key, window_seconds * 2)
    allowed = 1
end

return allowed
"""


class SlidingWindowCounterLimiter:
    def __init__(self, redis_client: redis.Redis, limit: int = 5, window_seconds: float = 5.0):
        self.redis = redis_client
        self.limit = limit
        self.window_seconds = window_seconds
        self._script = self.redis.register_script(SLIDING_WINDOW_COUNTER_LUA)

    def is_allowed(self, client_id: str) -> bool:
        key_prefix = f"sw_counter:{client_id}"
        now = time.time()

        result = self._script(
            keys=[key_prefix],
            args=[now, self.window_seconds, self.limit],
        )
        return result == 1
