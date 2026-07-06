import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class LinkCreate(BaseModel):
    """Request body for creating a short link."""
    url: HttpUrl
    custom_alias: str | None = Field(
        None,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Optional custom short code (alphanumeric, hyphens, underscores)",
    )
    expires_at: datetime | None = Field(
        None,
        description="Optional expiration datetime (UTC)",
    )


class LinkResponse(BaseModel):
    """Response for a shortened link."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    original_url: str
    short_url: str
    click_count: int
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None


class LinkListResponse(BaseModel):
    """Paginated list of links."""
    items: list[LinkResponse]
    total: int
    page: int
    size: int
    pages: int
