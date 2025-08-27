# All things auth live here: password hashing/verification,
# JWT creation/decoding, and a simple in-memory token revocation
# list for logout. It’s intentionally compact and dependency-light
# so you can reason about every moving part at a glance.

from datetime import datetime, timedelta
from typing import Any, Union
import logging

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings


# Safety check: we cannot mint or verify tokens without a secret.
# Fail fast on startup if SECRET_KEY is missing so we don’t end up
# issuing unsigned or invalid tokens by accident in production.
if not getattr(settings, "SECRET_KEY", None):
    raise RuntimeError(
        # SECRET_KEY environment variable must be set for token operations
    )

# Passlib gives us a nice, battle-tested wrapper for hashing and
# verifying passwords. Using bcrypt is a sane default and the
# context makes it easy to rotate schemes down the road.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Compare a user-supplied plaintext password with a stored hash.

    # This delegates to passlib’s constant-time verify under the hood,
    # which helps prevent timing attacks. Keep all password checking
    # funneled through this single function for consistency.
    
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    
    # Hash a plaintext password for storage.

    # We never store raw passwords. This returns a bcrypt hash that
    # includes its own salt. If we ever change algorithms, existing
    # hashes keep working because passlib records the scheme with the hash.
    
    return pwd_context.hash(password)


def create_access_token(
    data: dict[str, Any],
    expires_delta: Union[timedelta, None] = None
) -> str:
    
    # Create a signed JWT with an expiry.

    # The payload should at least include a 'sub' (subject/username).
    # We attach an 'exp' claim to enforce token expiry and sign with
    # our app secret + configured algorithm. Keep payloads minimal.
    
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logging.info("Issued token for %s: %s", data.get("sub"), token)
    return token


def decode_access_token(token: str) -> dict[str, Any]:
    
    # Decode and verify a JWT’s signature and claims.

    # If decoding fails (bad signature, expired, wrong alg), we raise
    # JWTError. Callers can catch and translate that into a 401. We log
    # both successes and failures to help with auditability.

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logging.info("Decoded token: %s", token)
        return payload
    except JWTError:
        logging.warning("Invalid token attempted: %s", token)
        raise


# Simple in-memory revocation list. This gives us a pragmatic
# way to “log out” JWTs without introducing a persistent store.
# For multi-instance deployments, swap this with Redis or DB.
revoked_tokens: set[str] = set()


def revoke_token(token: str) -> None:
    # Mark a JWT as revoked (used by /logout).

    # Any subsequent request presenting this exact token should be
    # rejected. Note that this set is in-memory, so restarts clear it—
    # use a shared cache if you need persistence across processes.
    revoked_tokens.add(token)


def is_token_revoked(token: str) -> bool:
    
    # Check if a token has been revoked.

    # Endpoints can call this alongside normal JWT verification to
    # enforce logouts. Returning True means “treat as invalid” even if
    # the signature and expiry are otherwise okay.

    return token in revoked_tokens
