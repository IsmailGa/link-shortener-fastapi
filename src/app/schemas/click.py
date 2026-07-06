from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClickEventResponse(BaseModel):
    """Individual click event."""
    model_config = ConfigDict(from_attributes=True)

    clicked_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    referrer: str | None = None


class DailyClickCount(BaseModel):
    """Click count for a single day."""
    date: str
    count: int


class LinkStatsResponse(BaseModel):
    """Aggregated statistics for a link."""
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    last_clicked_at: datetime | None = None
    daily_clicks: list[DailyClickCount]
    top_referrers: list[dict[str, int | str]]
    top_user_agents: list[dict[str, int | str]]
