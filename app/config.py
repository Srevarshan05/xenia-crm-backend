"""
Xenia CRM – Application Configuration
Centralised settings management via pydantic-settings.
All values are read from environment variables / .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_name: str = "Xenia CRM"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me"
    brand_name: str = "Xenia"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str

    # ── AI ────────────────────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    gemini_api_key: str = ""  # kept for backward compat, unused
    gemini_model: str = "llama-3.3-70b-versatile"  # alias kept for compat

    # ── ElevenLabs (Phase 2 Voice Campaigns) ─────────────────────────────────
    # Set ELEVENLABS_API_KEY in .env to enable real TTS audio synthesis.
    elevenlabs_api_key: str = ""                               # Phase 2 — leave empty for mock preview
    elevenlabs_voice_id_female: str = "EXAVITQu4vr4xnSDxMaL" # Xenia Voice (default)
    elevenlabs_voice_id_male: str = "VR6AewLTigWG4xSOukaG"   # Premium Male

    # ── Channel Service ───────────────────────────────────────────────────────
    channel_service_url: str = "http://localhost:8001"
    crm_webhook_url: str = "http://localhost:8000/api/webhook/delivery"

    # ── CORS ──────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    # ── ML ────────────────────────────────────────────────────────────────────
    churn_model_path: str = "ml/churn_model.joblib"
    churn_retrain_interval_days: int = 7

    # ── Attribution ───────────────────────────────────────────────────────────
    attribution_window_days: int = 7

    # ── Scheduler ─────────────────────────────────────────────────────────────
    briefing_hour_ist: int = 6        # 06:00 IST
    intelligence_hour_ist: int = 2    # 02:00 IST nightly


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()
