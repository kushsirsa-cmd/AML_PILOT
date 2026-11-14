from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://aml:aml@localhost:5432/aml"
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    # Set LLM_ENABLED=false to force the deterministic rules-only mode (no API calls).
    llm_enabled: bool = True
    cors_origins: str = "http://localhost:3000"
    seed_on_startup: bool = True
    # Demo authentication. Every demo user shares DEMO_PASSWORD. Set DEMO_OPEN_ACCESS=false to require a Bearer token on every call.
    demo_password: str = "demo1234"
    auth_secret: str = "change-me-in-production"
    demo_open_access: bool = True
    seed_size: str = "full"  # full = 100 customers / 50 businesses / 500 transactions; small = the original 11 customers + 5 corporates

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def llm_active(self) -> bool:
        return self.llm_enabled and bool(self.anthropic_api_key.strip())


settings = Settings()
