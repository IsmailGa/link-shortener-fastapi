import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository

logger = structlog.get_logger()


class AuthService:
    """Handles user registration, login, and token management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.token_repo = RefreshTokenRepository(db)

    async def register(self, email: str, password: str) -> dict:
        """Register a new user and return token pair.
        
        Raises:
            ValueError: If email is already registered.
        """
        if await self.user_repo.exists_by_email(email):
            raise ValueError("Email already registered")

        hashed = hash_password(password)
        user = await self.user_repo.create(email=email, hashed_password=hashed)

        # Generate token pair
        access_token = create_access_token(subject=str(user.id))
        refresh_token, jti, family_id = create_refresh_token(subject=str(user.id))

        # Store refresh token
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        await self.token_repo.create(
            user_id=user.id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
        )

        await self.db.commit()

        logger.info("user_registered", user_id=str(user.id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def login(self, email: str, password: str) -> dict:
        """Authenticate user and return token pair.
        
        Raises:
            ValueError: If credentials are invalid.
        """
        user = await self.user_repo.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise ValueError("Invalid email or password")

        if not user.is_active:
            raise ValueError("Account is deactivated")

        access_token = create_access_token(subject=str(user.id))
        refresh_token, jti, family_id = create_refresh_token(subject=str(user.id))

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        await self.token_repo.create(
            user_id=user.id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
        )

        await self.db.commit()

        logger.info("user_logged_in", user_id=str(user.id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh_tokens(self, refresh_token_str: str) -> dict:
        """Validate refresh token, rotate, and return new pair.
        
        Implements replay attack detection via token families.
        
        Raises:
            ValueError: If token is invalid, expired, or reused.
        """
        import jwt as pyjwt

        try:
            payload = decode_refresh_token(refresh_token_str)
        except pyjwt.ExpiredSignatureError:
            raise ValueError("Refresh token has expired")
        except pyjwt.InvalidTokenError:
            raise ValueError("Invalid refresh token")

        jti = payload.get("jti")
        family_id = payload.get("family_id")
        user_id_str = payload.get("sub")

        if not all([jti, family_id, user_id_str]):
            raise ValueError("Malformed refresh token")

        # Look up the token record
        token_record = await self.token_repo.get_by_jti(jti)

        if token_record is None:
            raise ValueError("Refresh token not found")

        if token_record.revoked:
            # REPLAY ATTACK: Revoke entire token family
            await self.token_repo.revoke_family(family_id)
            await self.db.commit()
            logger.warning(
                "refresh_token_replay_detected",
                jti=jti,
                family_id=family_id,
                user_id=user_id_str,
            )
            raise ValueError("Token reuse detected — all sessions revoked")

        # Revoke the current token
        await self.token_repo.revoke(jti)

        # Issue new pair in the same family
        user_id = uuid.UUID(user_id_str)
        new_access = create_access_token(subject=user_id_str)
        new_refresh, new_jti, _ = create_refresh_token(
            subject=user_id_str, family_id=family_id
        )

        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        await self.token_repo.create(
            user_id=user_id,
            jti=new_jti,
            family_id=family_id,
            expires_at=expires_at,
        )

        await self.db.commit()

        logger.info("tokens_refreshed", user_id=user_id_str)
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }
