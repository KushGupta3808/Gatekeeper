"""
GateKeeper - Circuit Breaker (Stage 5)

Protects the gateway (and the backend) from cascading failure: if a
backend keeps failing, stop calling it for a while instead of hammering
a service that's already struggling, then cautiously test recovery
before fully trusting it again.

Three states:
  CLOSED     - normal operation, requests flow through, failures counted
  OPEN       - tripped, requests fail instantly without even calling
               the backend, for `recovery_timeout` seconds
  HALF_OPEN  - after the timeout, let through a small number of test
               calls to check if the backend actually recovered before
               fully reopening

State transitions:
  CLOSED    -> OPEN       when failure_threshold consecutive failures happen
  OPEN      -> HALF_OPEN  after recovery_timeout seconds have passed
  HALF_OPEN -> CLOSED     when a test call succeeds
  HALF_OPEN -> OPEN       when a test call fails (start the cooldown over)

Per-instance state is intentional here, unlike the rate limiter - see
module docstring... err, see the note in the TRD / this file's header.
Each gateway instance tracks its own view of "is the backend healthy
from where I'm standing," which is a reasonable thing to keep local.
"""

import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None

    def _maybe_transition_to_half_open(self):
        """
        If we're OPEN and enough time has passed, move to HALF_OPEN so
        the next call gets treated as a test call instead of an
        automatic rejection.
        """
        if self.state == CircuitState.OPEN:
            elapsed_since_open = time.monotonic() - self.opened_at
            if elapsed_since_open >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN

    def call(self, func, *args, **kwargs):
        """
        Runs `func(*args, **kwargs)` through the breaker.

        - If CLOSED: call it normally, track success/failure.
        - If OPEN (and cooldown not done): reject immediately, don't
          even attempt the call - this is the entire point of the
          breaker, fail fast without touching the struggling backend.
        - If HALF_OPEN: allow exactly this one test call through and
          decide the next state based on whether it succeeds or fails.
        """
        self._maybe_transition_to_half_open()

        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                "Circuit is OPEN - backend considered unhealthy, rejecting without calling it"
            )

        try:
            result = func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            # the test call succeeded - backend looks recovered
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.opened_at = None
        elif self.state == CircuitState.CLOSED:
            # a normal successful call, reset any partial failure streak
            self.failure_count = 0

    def _on_failure(self):
        if self.state == CircuitState.HALF_OPEN:
            # the test call failed - still broken, go back to OPEN and
            # restart the full cooldown
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
        elif self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()