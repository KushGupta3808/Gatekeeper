"""
GateKeeper - Redis-backed Token Bucket Rate Limiter (Stage 2)

Fixes the bug from Stage 1: instead of each gateway instance keeping its
own private dict of buckets, ALL instances read/write the same bucket
state in Redis. There is now exactly one bucket per client, period,
regardless of how many gateway instances are running.

WHY A LUA SCRIPT INSTEAD OF PLAIN GET/SET:
Refilling and spending a token both need to happen together, atomically.
If we did this as separate GET, calculate, SET calls from Python, two
instances could both read the same starting state, both calculate
independently, and both write back a result - silently losing an update
(a classic race condition). Redis runs Lua scripts as a single atomic
operation: no other client's commands can interleave in the middle of
the script. This is the same idea as a database transaction, just
lighter-weight.
"""

import time
import redis


# This script runs ENTIRELY inside Redis, atomically:
#   KEYS[1] = the Redis key for this client's bucket (e.g. "bucket:kush")
#   ARGV[1] = capacity (max tokens)
#   ARGV[2] = refill_rate (tokens per second)
#   ARGV[3] = current timestamp (we pass this in from Python so Redis
#             doesn't need to know about wall-clock time itself)
#
# It stores two fields per client using a Redis HASH: "tokens" and
# "last_refill", does the same lazy-refill math as Stage 1, then either
# allows (decrements + returns 1) or rejects (returns 0).
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    -- first time we've ever seen this client: start with a full bucket
    tokens = capacity
    last_refill = now
end

-- lazy refill, same math as the naive Python version
local elapsed = now - last_refill
local refill_amount = elapsed * refill_rate
tokens = math.min(capacity, tokens + refill_amount)

local allowed = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
end

redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
-- expire the key if unused for a while, so we don't leak memory forever
-- on clients who never come back
redis.call("EXPIRE", key, 3600)

return allowed
"""


class RedisRateLimiter:
    """
    Same public interface as NaiveRateLimiter (is_allowed), but backed
    by Redis instead of an in-process dict. Any number of gateway
    instances can create one of these pointed at the same Redis and
    they will all correctly share state.
    """

    def __init__(self, redis_client: redis.Redis, capacity: int = 5, refill_rate: float = 1.0):
        self.redis = redis_client
        self.capacity = capacity
        self.refill_rate = refill_rate
        # Registering the script once and calling it by its SHA is more
        # efficient than sending the full script text on every request.
        self._script = self.redis.register_script(TOKEN_BUCKET_LUA)

    def is_allowed(self, client_id: str) -> bool:
        key = f"bucket:{client_id}"
        now = time.time()

        result = self._script(
            keys=[key],
            args=[self.capacity, self.refill_rate, now],
        )
        return result == 1
