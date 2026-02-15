from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "..."

    # JWT
    secret_key: str = "..."
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7

    # API
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # CORS
    backend_cors_origins: str = ""

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None  # ← Optional
    smtp_password: str | None = None  # ← Optional  
    smtp_from: str | None = None
    otp_subject: str = "Authorization code"

    app_host: str = "localhost"
    app_port: int =  8070

    device_id: str = "69728ef652ef775390b32f83"
    phone: str = "+995511221503"
    apikey: str = "0f0f0dad-ce62-4ffa-b1e3-76634a59eb67"
    kafka_bootstrap_servers: str = ""
    tg_api_id: str = ""
    tg_api_hash: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if not self.backend_cors_origins:
            return []
        return [origin.strip() for origin in self.backend_cors_origins.split(",")]


settings: Settings = Settings()

