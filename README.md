# GateKeeper

A distributed API gateway built from scratch — rate limiting, JWT auth, circuit breaking, and observability, the layer that sits in front of production services at companies like Stripe and Cloudflare.

**Status:** Feature-complete (v1)

## Why this project

Full docs (problem statement, architecture, algorithm tradeoffs) live in [`/docs`](./docs):
- [PRD](./docs/PRD.md) — what and why
- [TRD](./docs/TRD.md) — architecture and technical decisions
- [Load Test Results](./docs/LOAD_TEST_RESULTS.md) — measured behavior under concurrent load

## What it does

- **Rate limits** clients using one of three swappable algorithms (token bucket, sliding window log, sliding window counter), all Redis-backed so limits hold correctly across multiple gateway instances — not just one.
- **Authenticates** clients via JWT, so rate limits key off a verified identity, not a spoofable query param.
- **Protects backends** with a Closed/Open/Half-Open circuit breaker: stops hammering a failing backend, then cautiously tests recovery instead of blindly resuming full traffic.
- **Exposes Prometheus metrics** (request outcomes, latency histogram, circuit breaker state) for real-time observability via Grafana.
- **Proven under load**: 1,400+ concurrent requests via Locust, 0 genuine failures, p95 latency of 6ms. See [full results](./docs/LOAD_TEST_RESULTS.md).

## Architecture

```
Client → JWT auth → Rate limiter (Redis, swappable algorithm)
                   → Circuit breaker → Backend
                   ↓
              Prometheus metrics (/metrics)
```

Every gateway instance shares rate-limit state via Redis (see `docs/TRD.md` Section 2 for why this matters — the naive in-memory version silently multiplies the intended limit by however many instances are running).

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Redis required (separately):
redis-server

uvicorn app.main:app --reload --port 8000
```

### Try it

```bash
# 1. Get a token
curl "http://localhost:8000/auth/token?client_id=kush"

# 2. Call the protected endpoint
curl http://localhost:8000/api/data -H "Authorization: Bearer <token>"

# 3. Watch metrics
curl http://localhost:8000/metrics
```

Swap the rate-limiting algorithm via env var:
```bash
RATE_LIMIT_ALGORITHM=sliding_window_counter uvicorn app.main:app --port 8000
```

### Observability stack

```bash
docker compose up
```
Prometheus: `http://localhost:9090` · Grafana: `http://localhost:3000` (admin/admin)

### Load test

```bash
locust -f locustfile.py --host http://localhost:8000 \
    --headless -u 30 -r 10 -t 15s \
    --csv=docs/load_test_results --html=docs/load_test_report.html
```

## Roadmap

- [x] Naive in-memory token bucket (and the multi-instance bug it demonstrates)
- [x] Redis-backed distributed token bucket
- [x] Sliding window log + sliding window counter algorithms
- [x] JWT authentication
- [x] Circuit breaker
- [x] Prometheus + Grafana observability
- [x] Load testing with Locust

### Possible next steps
- [ ] Frontend dashboard (stretch)
- [ ] Docker Compose for the gateway itself, multi-instance (stretch — proves distributed correctness via containers, not just multiple local ports)
- [ ] Kubernetes deployment (stretch)
