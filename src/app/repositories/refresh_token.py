import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken

logger = structlog.get_logger()


class RefreshTokenRepository:
    """Database operations for RefreshToken model."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        user_id: uuid.UUID,
        jti: str,
        family_id: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Store a new refresh token record."""
        token = RefreshToken(
            user_id=user_id,
            jti=jti,
            family_id=family_id,
            expires_at=expires_at,
        )
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        """Fetch a refresh token by its JTI claim."""
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        return result.scalar_one_or_none()

    async def revoke(self, jti: str) -> bool:
        """Revoke a single refresh token. Returns True if found."""
        result = await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(revoked=True)
        )
        return result.rowcount > 0

    async def revoke_family(self, family_id: str) -> int:
        """Revoke ALL tokens in a family (replay attack response)."""
        result = await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True)
        )
        count = result.rowcount
        if count > 0:
            logger.warning(
                "token_family_revoked",
                family_id=family_id,
                tokens_revoked=count,
            )
        return count

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> int:
        """Revoke ALL refresh tokens for a user (security escalation)."""
        result = await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
            .values(revoked=True)
        )
        count = result.rowcount
        logger.warning(
            "all_user_tokens_revoked",
            user_id=str(user_id),
            tokens_revoked=count,
        )
        return count

    async def cleanup_expired(self) -> int:
        """Delete expired refresh tokens from the database."""
        from sqlalchemy import delete as sa_delete
        result = await self.db.execute(
            sa_delete(RefreshToken).where(
                RefreshToken.expires_at < datetime.now(timezone.utc)
            )
        )
        return result.rowcount
