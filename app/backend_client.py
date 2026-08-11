"""
GateKeeper - Simulated backend (Stage 5 demo helper)

Stands in for a real backend service the gateway would proxy to. Has a
global on/off switch so we can flip it "broken" on demand and watch the
circuit breaker react through real HTTP calls, not just an isolated
test script.
"""

_backend_healthy = True


def set_backend_healthy(healthy: bool):
    global _backend_healthy
    _backend_healthy = healthy


def call_backend(client_id: str) -> dict:
    """The actual 'work' the gateway would normally proxy to a real service."""
    if not _backend_healthy:
        raise Exception("simulated backend failure")
    return {"client_id": client_id, "data": "here's your data"}