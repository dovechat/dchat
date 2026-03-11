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
    manager_subject: str = "Invitation to DChat"

    app_host: str = "localhost"
    app_port: int =  8070

    device_id: str = "69728ef652ef775390b32f83"
    phone: str = "+995511221503"
    apikey: str = "0f0f0dad-ce62-4ffa-b1e3-76634a59eb67"
    kafka_bootstrap_servers: str = ""
    kafka_topic: str = ""
    kafka_group_id: str = ""
    tg_api_id: str = ""
    tg_api_hash: str = ""
    tg_webhook_url: str = ""

    s3_endpoint: str = "minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_secure: bool = False
    s3_bucket: str = "dovechat-media"
    s3_external_url: str = "http://localhost:9000/dovechat-media/"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        if not self.backend_cors_origins:
            return []
        return [origin.strip() for origin in self.backend_cors_origins.split(",")]


settings: Settings = Settings()

