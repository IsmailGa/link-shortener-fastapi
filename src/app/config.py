from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "link-shortener"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    base_url: str = "http://localhost:8000"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "shortener"
    postgres_password: str = "shortener_secret"
    postgres_db: str = "shortener"

    @computed_field
    @property
    def database_url(self) -> str:
        """Build async PostgreSQL connection URL from individual components."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # JWT
    jwt_access_secret: str = "your-access-secret-key-min-32-chars"
    jwt_refresh_secret: str = "your-refresh-secret-key-min-32-chars"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # Rate Limiting
    anon_rate_limit_per_day: int = 50

    # Cleanup
    link_inactive_days: int = 30
    cleanup_cron_hour: int = 3
    cleanup_cron_minute: int = 0

    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if the application is running in production mode."""
        return self.app_env == "production"


settings = Settings()
