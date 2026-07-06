import uuid
from typing import Annotated

import jwt as pyjwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_manager
from app.core.security import decode_access_token
from app.db.session import async_session_factory
from app.models.user import User
from app.repositories.user import UserRepository

logger = structlog.get_logger()

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    """Provide an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_redis():
    """Provide the Redis client."""
    return redis_manager.client


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Extract and validate the current user from JWT.
    
    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
        HTTPException 401: If user not found or inactive.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except pyjwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(uuid.UUID(user_id_str))

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Extract current user if token is provided, None otherwise.
    
    Does not raise on missing token — used for endpoints that
    work for both authenticated and anonymous users.
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None

    user_id_str = payload.get("sub")
    if not user_id_str:
        return None

    user_repo = UserRepository(db)
    return await user_repo.get_by_id(uuid.UUID(user_id_str))


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request.
    
    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to direct client IP.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (original client)
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
