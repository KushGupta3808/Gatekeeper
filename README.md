# GateKeeper

A distributed API gateway built from scratch — rate limiting, auth, circuit breaking, and observability, the layer that sits in front of production services at companies like Stripe and Cloudflare.

**Status:** In progress (Stage 1 — naive single-instance rate limiter)

## Why this project

Full docs (problem statement, architecture, algorithm tradeoffs) live in [`/docs`](./docs):
- [PRD](./docs/PRD.md) — what and why
- [TRD](./docs/TRD.md) — architecture and technical decisions

## Current state

Stage 1: single-process token bucket rate limiter, deliberately built without shared state first, to demonstrate why in-memory rate limiting breaks across multiple instances. See `docs/TRD.md` Section 2.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Test it:
```bash
curl "http://localhost:8000/api/data?client_id=kush"
```

## Roadmap

- [x] Naive in-memory token bucket
- [ ] Redis-backed distributed token bucket
- [ ] Sliding window log + sliding window counter algorithms
- [ ] JWT authentication
- [ ] Circuit breaker
- [ ] Prometheus + Grafana observability
- [ ] Load testing with Locust
