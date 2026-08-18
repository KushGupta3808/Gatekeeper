"""
GateKeeper - Load test (Stage 7)

Simulates many concurrent clients hitting the gateway, to observe real
behavior under load rather than just trusting the design.

Each simulated Locust "user" represents one client:
  1. on_start(): gets its own JWT once, like a real client logging in
     once and reusing the token (not re-authenticating every request).
  2. task: repeatedly calls /api/data with that token.

IMPORTANT DESIGN CHOICE - what counts as a "failure" here:
A 429 (rate limited) is NOT a bug - it's the rate limiter doing
exactly its job under heavy load. If we let Locust count 429s as
failures by default, our results would look like the system is
broken when it's actually working correctly. So we explicitly mark
429 responses as successful in Locust's eyes, and rely on the
request-count breakdown (visible in the HTML report) to see how many
were rate-limited vs actually allowed. A genuine failure (502, 503,
connection error, 500) still counts as a failure, since those
represent the system actually breaking down, not enforcing a limit.

Run against a running gateway (make sure Redis + uvicorn are up):
    locust -f locustfile.py --host http://localhost:8000

Or headless, for a scripted N-second run producing a report:
    locust -f locustfile.py --host http://localhost:8000 \
        --headless -u 50 -r 10 -t 30s \
        --csv=docs/load_test_results --html=docs/load_test_report.html

    -u 50   -> simulate 50 concurrent users total
    -r 10   -> spawn 10 new users per second, ramping up to 50
    -t 30s  -> run for 30 seconds total
"""

import uuid

from locust import HttpUser, task, between


class GatewayUser(HttpUser):
    # each simulated user waits 0.1-0.5s between requests, so we're
    # not sending every user's requests in perfect lockstep
    wait_time = between(0.1, 0.5)

    def on_start(self):
        # give each simulated user a unique client_id, so they don't
        # all share (and fight over) the same rate limit bucket
        self.client_id = f"loadtest-{uuid.uuid4().hex[:8]}"

        response = self.client.get(
            f"/auth/token?client_id={self.client_id}",
            name="/auth/token",
        )
        self.token = response.json()["access_token"]

    @task
    def call_api(self):
        with self.client.get(
            "/api/data",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/data",
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                # rate limiter doing its job under load - not a failure
                response.success()
            elif response.status_code == 200:
                response.success()
            else:
                # 502 (backend error), 503 (circuit open), or anything
                # else genuinely IS a failure worth flagging
                response.failure(f"unexpected status {response.status_code}")
