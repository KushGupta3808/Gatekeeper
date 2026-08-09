"""
GateKeeper - JWT Authentication (Stage 4)

Provides two things:
  - create_token(client_id): issues a signed JWT for a client, standing
    in for "the notary writing and sealing the letter." In a real
    system this would happen after a proper login/API-key exchange -
    here we expose it directly via /auth/token for demo purposes.
  - decode_token(token): verifies a JWT's signature and extracts the
    client_id from it - "checking the wax seal is genuinely ours."

WHY THIS MATTERS FOR THE GATEWAY:
Rate limiting only means something if we trust WHO we're limiting.
Before this stage, client_id came from a query param anyone could type
in. Now client_id comes from inside a signed token that only this
server could have issued, so a client can't just claim to be someone
else to dodge their own rate limit.

SECRET_KEY note: in a real deployment this would come from an
environment variable / secrets manager, never hardcoded. It's
hardcoded here only because this is a local demo project.
"""

import time
import jwt
from fastapi import Header, HTTPException

SECRET_KEY = "gatekeeper-demo-secret-do-not-use-in-production"
ALGORITHM = "HS256"          # HMAC + SHA-256, a standard symmetric signing algorithm
TOKEN_EXPIRY_SECONDS = 3600   # tokens are valid for 1 hour


def create_token(client_id: str) -> str:
    """Builds and signs a JWT for the given client_id."""
    payload = {
        "client_id": client_id,
        "iat": int(time.time()),                      # "issued at" timestamp
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS, # expiry timestamp
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> str:
    """
    Verifies the token's signature and expiry, returns the client_id
    inside it. Raises jwt exceptions if the token was tampered with,
    signed with the wrong key, or has expired - jwt.decode checks the
    signature BEFORE handing back any payload data, so a forged token
    never gets this far.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["client_id"]


def get_client_id_from_header(authorization: str = Header(...)) -> str:
    """
    FastAPI dependency: pulls the token out of the Authorization header
    (expected format: "Bearer <token>"), verifies it, and returns the
    client_id. Used as a dependency on any endpoint that needs to know
    WHO is calling, not just trust a claimed identity.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        return decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")