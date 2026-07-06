import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
)
from app.services.auth import AuthService

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account and return JWT token pair."""
    service = AuthService(db)
    try:
        result = await service.register(email=body.email, password=body.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return result


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login with credentials",
)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email and password, receive JWT token pair."""
    service = AuthService(db)
    try:
        result = await service.login(email=body.email, password=body.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return result


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new token pair.

    Implements refresh token rotation with replay attack detection.
    """
    service = AuthService(db)
    try:
        result = await service.refresh_tokens(body.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return result
