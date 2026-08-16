"""
GateKeeper - Metrics (Stage 6)

Defines the actual numbers we track, using prometheus_client's types.
These objects live in memory and get updated as requests happen - they
don't send anything anywhere by themselves. Prometheus (the separate
server) is what will later come and READ these numbers by visiting
our /metrics endpoint (see main.py), on its own schedule.

Three metric types used here, matching the three concepts described
before writing any code:

Counter  - only ever goes up. Good for "total X that happened."
Gauge    - goes up AND down. Good for "current state right now."
Histogram - buckets of measurements. Good for "distribution of request
            durations," letting you ask about p50/p95/p99 later, not
            just an average that can hide bad outliers.
"""

from prometheus_client import Counter, Gauge, Histogram

# Counter: total requests, labeled by outcome, so we can see
# allowed vs rate-limited vs backend-error vs circuit-open, separately,
# without needing four different counters.
requests_total = Counter(
    "gatekeeper_requests_total",
    "Total requests handled by the gateway, by outcome",
    ["outcome"],  # a "label" - lets us slice this one counter by outcome
)

# Gauge: is the circuit breaker currently open? 1 = open, 0 = closed.
# This is "current state," so it needs to be able to go back down to 0,
# which is exactly what a Gauge (not a Counter) is for.
circuit_breaker_open = Gauge(
    "gatekeeper_circuit_breaker_open",
    "Whether the circuit breaker is currently open (1) or not (0)",
)

# Histogram: how long each request took, in seconds. Prometheus will
# bucket these automatically (e.g. how many requests took <0.01s,
# <0.05s, <0.1s, etc), which is what lets Grafana later draw p95/p99
# latency graphs instead of just a single average number.
request_duration_seconds = Histogram(
    "gatekeeper_request_duration_seconds",
    "Time spent handling each request, in seconds",
)
