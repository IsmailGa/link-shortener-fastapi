from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness check response."""
    status: str = "ok"
    version: str = "0.1.0"


class ServiceStatus(BaseModel):
    """Status of an individual service dependency."""
    name: str
    status: str  # "ok" or "error"
    latency_ms: float | None = None
    error: str | None = None


class ReadinessResponse(BaseModel):
    """Readiness check with dependency statuses."""
    status: str  # "ok" or "degraded"
    services: list[ServiceStatus]
