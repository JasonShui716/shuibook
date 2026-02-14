from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field("postgresql+psycopg2://postgres:postgres@postgres:5432/shuibook", alias="DATABASE_URL")
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")

    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-5-mini", alias="OPENAI_MODEL")
    translate_fulltext: bool = Field(True, alias="TRANSLATE_FULLTEXT")
    translation_model: str = Field("gpt-4o-mini", alias="TRANSLATE_MODEL")
    translation_chunk_chars: int = Field(1200, alias="TRANSLATION_CHUNK_CHARS")
    translation_ttl_hours: int = Field(72, alias="TRANSLATION_TTL_HOURS")
    clean_model: str = Field("gpt-4o-mini", alias="CLEAN_MODEL")
    clean_max_chars: int = Field(12000, alias="CLEAN_MAX_CHARS")
    retention_days: int = Field(5, alias="RETENTION_DAYS")
    max_item_age_days: int = Field(60, alias="MAX_ITEM_AGE_DAYS")

    api_base_url: str = Field("http://localhost:8000", alias="API_BASE_URL")
    web_base_url: str = Field("http://localhost:3000", alias="WEB_BASE_URL")

    max_items_per_run: int = Field(100, alias="MAX_ITEMS_PER_RUN")
    scheduled_max_items: int = Field(30, alias="SCHEDULED_MAX_ITEMS")
    manual_max_items: int = Field(50, alias="MANUAL_MAX_ITEMS")
    manual_source_max_items: int = Field(10, alias="MANUAL_SOURCE_MAX_ITEMS")
    max_candidates_per_source: int = Field(60, alias="MAX_CANDIDATES_PER_SOURCE")
    max_forum_candidates_per_source: int = Field(12, alias="MAX_FORUM_CANDIDATES_PER_SOURCE")
    strict_signal_filter: bool = Field(True, alias="STRICT_SIGNAL_FILTER")
    filter_forum_sources: bool = Field(True, alias="FILTER_FORUM_SOURCES")
    min_summary_input_chars: int = Field(450, alias="MIN_SUMMARY_INPUT_CHARS")
    min_summary_input_paragraphs: int = Field(3, alias="MIN_SUMMARY_INPUT_PARAGRAPHS")
    min_summary_chars: int = Field(320, alias="MIN_SUMMARY_CHARS")
    min_summary_bullets: int = Field(3, alias="MIN_SUMMARY_BULLETS")
    min_practical_takeaways: int = Field(2, alias="MIN_PRACTICAL_TAKEAWAYS")
    excerpt_max_chars: int = Field(2000, alias="EXCERPT_MAX_CHARS")
    rate_limit_seconds: float = Field(30.0, alias="RATE_LIMIT_SECONDS")
    user_agent: str = Field("ShuiBookBot/1.0 (+https://example.com)", alias="USER_AGENT")
    download_images: bool = Field(False, alias="DOWNLOAD_IMAGES")
    media_dir: str = Field("/data/media", alias="MEDIA_DIR")
    log_dir: str = Field("/data/logs", alias="LOG_DIR")

    timezone: str = Field("Asia/Singapore", alias="TZ")

    hn_comments_limit: int = Field(20, alias="HN_COMMENTS_LIMIT")
    brave_search_api_key: str | None = Field(None, alias="BRAVE_SEARCH_API_KEY")
    newsapi_key: str | None = Field(None, alias="NEWSAPI_KEY")
    firecrawl_api_key: str | None = Field(
        None,
        validation_alias=AliasChoices("FIRECRAWL_API_KEY", "FIRECRAWL_KEY", "FIRECRAL_KEY"),
    )
    producthunt_token: str | None = Field(
        None, validation_alias=AliasChoices("PRODUCTHUNT_TOKEN", "PRODUCT_HUNT_TOKEN")
    )
    producthunt_key: str | None = Field(
        None, validation_alias=AliasChoices("PH_KEY", "PRODUCTHUNT_KEY", "PRODUCT_HUNT_KEY")
    )
    producthunt_secret: str | None = Field(
        None,
        validation_alias=AliasChoices(
            "PH_SECRET", "PRODUCTHUNT_SECRET", "PRODUCT_HUNT_SECRET"
        ),
    )

    medium_rate_limit_seconds: float = Field(3.0, alias="MEDIUM_RATE_LIMIT_SECONDS")

    allow_speculation: bool = Field(False, alias="ALLOW_SPECULATION")
    remote_fetch_enabled: bool = Field(False, alias="REMOTE_FETCH_ENABLED")
    remote_fetch_host: str | None = Field(None, alias="REMOTE_FETCH_HOST")
    remote_fetch_user: str = Field("ubuntu", alias="REMOTE_FETCH_USER")
    remote_fetch_port: int = Field(22, alias="REMOTE_FETCH_PORT")
    remote_fetch_key_path: str = Field(
        "/root/.ssh/id_remote_fetch", alias="REMOTE_FETCH_KEY_PATH"
    )
    remote_fetch_timeout: int = Field(30, alias="REMOTE_FETCH_TIMEOUT")
    remote_fetch_max_bytes: int = Field(5_000_000, alias="REMOTE_FETCH_MAX_BYTES")

    admin_totp_secret: str | None = Field(None, alias="ADMIN_TOTP_SECRET")
    admin_session_ttl_hours: int = Field(8, alias="ADMIN_SESSION_TTL_HOURS")
    admin_otp_ip_max_attempts: int = Field(5, alias="ADMIN_OTP_IP_MAX_ATTEMPTS")
    admin_otp_ip_window_seconds: int = Field(300, alias="ADMIN_OTP_IP_WINDOW_SECONDS")
    admin_otp_ip_lock_seconds: int = Field(900, alias="ADMIN_OTP_IP_LOCK_SECONDS")
    admin_otp_global_max_attempts: int = Field(20, alias="ADMIN_OTP_GLOBAL_MAX_ATTEMPTS")
    admin_otp_global_window_seconds: int = Field(3600, alias="ADMIN_OTP_GLOBAL_WINDOW_SECONDS")
    admin_otp_global_lock_seconds: int = Field(3600, alias="ADMIN_OTP_GLOBAL_LOCK_SECONDS")


settings = Settings()
