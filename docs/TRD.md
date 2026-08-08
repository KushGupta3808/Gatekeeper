# GateKeeper — Technical Requirements Document (TRD)

**Status:** Draft v1
**Last updated:** August 2026

---

## 1. Architecture Overview

```
                     ┌─────────────────────────────┐
                     │        Client / User         │
                     └──────────────┬───────────────┘
                                    │ HTTP request + API key/JWT
                                    ▼
              ┌─────────────────────────────────────────┐
              │            GateKeeper Gateway             │
              │  (1 or more instances, load balanced)     │
              │                                             │
              │  1. Authenticate (JWT)                     │
              │  2. Check rate limit  ───► Redis (shared)  │
              │  3. Check circuit breaker state             │
              │  4. Proxy to backend OR reject (429/503)   │
              │  5. Log + emit metrics                     │
              └──────────────┬──────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              Backend Service A   Backend Service B
                  (mock/demo)         (mock/demo)
```

Redis sits alongside the gateway instances as **shared state** — this is the single most important architectural decision in this project, covered in detail in Section 3.

## 2. Why Not "Just a Dictionary"?

The naive rate limiter looks like this:

```python
request_counts = {}  # {client_id: count}

def is_allowed(client_id):
    request_counts[client_id] = request_counts.get(client_id, 0) + 1
    return request_counts[client_id] <= LIMIT
```

This works — on **one process**. The moment you run 2+ instances of the gateway behind a load balancer (which any real deployment does, for redundancy and throughput), each instance has its *own* `request_counts` dictionary in its *own* memory. A client hammering the API gets routed round-robin across instances, and each instance thinks it's only seeing a fraction of the traffic. The client can now send `LIMIT × number_of_instances` requests before anything blocks them — the limit is silently multiplied by however many servers you're running.

This is the exact bug that makes "rate limiting" a distributed-systems problem, not just an algorithms problem. It's why Redis (or another shared, low-latency store) sits in the architecture — every gateway instance checks and updates the *same* counter, so the limit holds no matter how many instances are running or which one a request lands on.

We'll build it in two stages on purpose: naive in-memory first (so you feel the bug happen), then Redis-backed (so the fix is obvious and memorable — not just told to you).

## 3. Rate-Limiting Algorithms

### 3.1 Token Bucket
**Analogy:** A bucket holds up to N tokens. It refills at a fixed rate (e.g., 10 tokens/second). Every request costs 1 token. Empty bucket → request rejected (or queued). Because the bucket can hold up to N tokens even during idle time, it naturally allows short bursts, then smooths out.

- **Pros:** Allows bursts (good UX — a client that's been quiet can send a quick flurry). Cheap to compute (a couple of numbers per client).
- **Cons:** Burst allowance can be abused right at the edge of two windows if not careful.
- **Where it's used:** AWS API Gateway, Stripe's public API.

### 3.2 Sliding Window Log
**Analogy:** Keep a literal timestamped log of every request in the last N seconds for a client. To check a new request, count how many timestamps fall inside the current window.

- **Pros:** Perfectly accurate — no edge-case bursts possible.
- **Cons:** Memory grows with request volume (storing every timestamp). Expensive at scale.

### 3.3 Sliding Window Counter
**Analogy:** Instead of logging every request, keep two fixed counters — "previous window" and "current window" — and estimate the sliding count as a weighted average based on how far into the current window we are.

- **Pros:** Near-accurate, but O(1) memory per client instead of O(requests).
- **Cons:** Slight approximation error (acceptable in practice — this is what most real systems use).
- **Where it's used:** Cloudflare, most production API gateways — this is the industry-standard middle ground.

**We implement all three, config-swappable**, specifically so you can speak to the tradeoffs rather than just having built "a" rate limiter.

## 4. Circuit Breaker

**Analogy:** A home electrical breaker. If a backend service starts failing repeatedly, the gateway "trips" — stops sending it traffic entirely for a cooldown period — instead of continuing to hammer a service that's already struggling (which makes outages worse, not better). After the cooldown, it sends a small number of "trial" requests; if they succeed, it closes the circuit and resumes normal traffic.

States: **Closed** (normal) → **Open** (tripped, rejecting immediately) → **Half-Open** (testing recovery) → back to Closed or Open.

## 5. Authentication

JWT-based. Each client gets a signed token identifying them; the gateway validates the signature and extracts a client ID, which becomes the key used for rate-limit tracking. This also means rate limits can be tiered later (e.g., free vs. paid client) without changing the core algorithm — just the limit value looked up per client.

## 6. Observability

- **Structured logs** (JSON) for every request: client ID, decision (allowed/rejected), latency, backend routed to.
- **Prometheus metrics:** request rate, rejection rate, latency histograms, circuit breaker state changes.
- **Grafana dashboard:** visualize the above in real time — this is what makes the load test results "provable" rather than just claimed.

## 7. Tech Stack & Justification

| Component | Choice | Why |
|---|---|---|
| Gateway framework | FastAPI | Async support matters here — gateway is I/O-bound (waiting on Redis + backend calls) |
| Shared state | Redis | Sub-millisecond reads/writes, atomic increment operations, industry standard for this exact use case |
| Load testing | Locust | Python-native, easy to script realistic traffic patterns |
| Metrics | Prometheus + Grafana | Industry-standard observability pairing, directly resume-relevant |
| Multi-instance simulation | Docker Compose | Enough to prove distributed correctness without K8s overhead |

## 8. Data Flow — Single Request Lifecycle

1. Request hits gateway with `Authorization: Bearer <JWT>`.
2. Gateway validates JWT → extracts `client_id`.
3. Gateway checks circuit breaker state for target backend — if open, reject immediately (503).
4. Gateway checks rate limit for `client_id` against Redis — if exceeded, reject (429) with `Retry-After` header.
5. Gateway proxies request to backend.
6. Backend response returned to client; circuit breaker updated (success/failure); metrics + logs emitted.

## 9. Testing Strategy

- Unit tests per algorithm (token bucket, sliding window log, sliding window counter) — verify correctness in isolation.
- Integration test: multiple gateway instances + shared Redis, verify limit holds correctly across instances.
- Load test: Locust script simulating burst + sustained traffic, documented results (RPS handled, rejection accuracy, p95/p99 latency).
