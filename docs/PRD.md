# GateKeeper — Product Requirements Document (PRD)

**Author:** Kush Gupta
**Status:** Draft v1
**Last updated:** August 2026

---

## 1. Overview

GateKeeper is a distributed API gateway that sits in front of backend services and handles the cross-cutting concerns every production system needs before a request ever reaches business logic: **rate limiting, authentication, request queuing, and observability.**

Instead of building another product with a UI, this project builds the *infrastructure layer* that companies like Stripe, Atlassian, Amazon, and Cloudflare run in front of thousands of internal services. It's the part of the stack most CS students never touch — which is exactly why it's valuable to show.

## 2. Problem Statement

Every API that receives traffic from more than one client eventually needs to answer:
- How do we stop one client from overwhelming the system? (rate limiting)
- How do we know *who* is calling us? (authentication)
- What happens when we're at capacity — reject, queue, or degrade? (backpressure)
- How do we know the system is healthy right now, not just when it crashes? (observability)

Most portfolio projects skip this layer entirely because it's invisible — there's no UI for a rate limiter. But it's disproportionately what backend/infra interviews and take-home assessments test, because it's foundational to running anything at scale.

## 3. Objectives

1. Build a working API gateway that can sit in front of any backend service and enforce rate limits per client.
2. Implement and be able to explain, from first principles, at least three rate-limiting algorithms (token bucket, sliding window log, sliding window counter) — including their tradeoffs.
3. Demonstrate distributed-systems awareness: rate limits must hold correctly even when the gateway runs as multiple instances (shared state via Redis, not in-memory per-instance state).
4. Add production-grade concerns: JWT-based auth, circuit breaking for unhealthy backends, structured logging, and metrics (Prometheus + Grafana).
5. Prove it under load — a load test (Locust or k6) showing the gateway holding its guarantees at volume, with results documented.
6. Ship full documentation (this PRD, a TRD, README, learning log) at the same bar as METRO AI, so the project is defensible in a live interview.

## 4. Non-Objectives (out of scope for v1)

- No frontend/UI. This is a backend infra project — a dashboard is a stretch goal only if time allows.
- No real backend services behind the gateway — we'll proxy to 1-2 dummy/mock APIs (or reuse a simplified METRO AI endpoint) to demonstrate proxying, not build new products.
- No Kubernetes/container orchestration in v1 — Docker Compose is sufficient to prove multi-instance behavior. K8s can be a stretch goal.
- No custom load balancing algorithm — we'll use round-robin or least-connections from an existing library where reasonable; the focus is rate limiting and gateway behavior, not reinventing load balancers.

## 5. Target "User"

This is a portfolio/infra project, so the "user" is twofold:
- **Any backend service** that wants rate limiting, auth, and observability without building it into every microservice individually (the real-world use case for gateways).
- **The interviewer/recruiter** reading the project — it needs to read clearly as "this person understands distributed systems," not just "this person can write Python."

## 6. Core Concepts We'll Cover (plain-language preview — full depth in TRD)

- **Token Bucket** — think of a bucket that refills with tokens at a fixed rate; each request costs a token; empty bucket = request rejected or queued. Good for allowing bursts.
- **Sliding Window Log** — keep a timestamped log of every request in the last N seconds; count them to decide if a new one is allowed. Precise, but memory-heavy.
- **Sliding Window Counter** — a cheaper approximation of the sliding window using two fixed windows and a weighted count. The industry-standard tradeoff between accuracy and cost.
- **Circuit Breaker** — like a home electrical breaker: if a backend keeps failing, "trip" and stop sending it traffic for a cooldown period, instead of hammering a dying service.
- **Distributed state via Redis** — why rate limits break if each gateway instance tracks its own counters in memory, and how a shared store fixes it.

## 7. Success Criteria

- [ ] Gateway correctly rate-limits per client/API key across 3+ concurrent gateway instances (proves distributed correctness, not just single-node).
- [ ] All three rate-limiting algorithms implemented, swappable via config, each with a written explanation of tradeoffs.
- [ ] Load test report showing behavior at scale (requests/sec handled, rejection behavior under burst, latency under load).
- [ ] Full documentation set (PRD, TRD, README, learning log) matching METRO AI's bar.
- [ ] You can explain every design decision out loud, unscripted, in under 2 minutes per component.

## 8. Timeline (3–4 weeks, real depth)

| Week | Focus |
|---|---|
| 1 | Core gateway skeleton + single-node token bucket rate limiter, fully understood before moving on |
| 2 | Sliding window algorithms, Redis-backed distributed state, multi-instance correctness |
| 3 | Auth (JWT), circuit breaker, structured logging, metrics (Prometheus/Grafana) |
| 4 | Load testing, documentation polish, README, demo recording |

## 9. Tech Stack (proposed — confirmed in TRD)

- **Language/Framework:** Python + FastAPI
- **Shared state:** Redis
- **Load testing:** Locust
- **Observability:** Prometheus + Grafana
- **Containerization:** Docker Compose (multi-instance simulation)
- **Auth:** JWT (PyJWT)
