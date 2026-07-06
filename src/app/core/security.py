import uuid
from datetime import datetime, timedelta, timezone

import jwt
import structlog
import bcrypt

from app.config import settings

logger = structlog.get_logger()


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(subject: str) -> str:
    """Create a short-lived JWT access token.

    Args:
        subject: The user ID (as string) to encode in the token.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "access",
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_access_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, family_id: str | None = None) -> tuple[str, str, str]:
    """Create a long-lived JWT refresh token with family tracking.

    Args:
        subject: The user ID (as string).
        family_id: Token family ID for rotation tracking. Generated if None.

    Returns:
        Tuple of (encoded_token, jti, family_id).
    """
    jti = str(uuid.uuid4())
    if family_id is None:
        family_id = str(uuid.uuid4())

    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "family_id": family_id,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_refresh_secret, algorithm=settings.jwt_algorithm)
    return token, jti, family_id


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token.

    Raises:
        jwt.ExpiredSignatureError: If token has expired.
        jwt.InvalidTokenError: If token is invalid.
    """
    payload = jwt.decode(
        token, settings.jwt_access_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Token type is not 'access'")
    return payload


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a refresh token.

    Raises:
        jwt.ExpiredSignatureError: If token has expired.
        jwt.InvalidTokenError: If token is invalid.
    """
    payload = jwt.decode(
        token, settings.jwt_refresh_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Token type is not 'refresh'")
    return payload
