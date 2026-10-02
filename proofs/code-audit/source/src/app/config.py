"""Server settings; provider keys stay in .env and never travel to the browser."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_DOCKING_", env_file=".env", extra="ignore")
    mode: str = "vertex"
    llm_model: str = "gpt-4o"
    llm_model_groq: str = "llama-3.1-8b-instant"
    llm_model_openrouter: str = "meta-llama/llama-3.1-8b-instant"
    llm_model_vertex: str = "gemini-3.8-flash"
    llm_base_url: str | None = None
    llm_timeout_s: float = Field(default=60.0, gt=0.0, le=120.0)
    llm_max_retries: int = Field(default=1, ge=0, le=3)
    llm_retry_backoff_s: float = Field(default=0.25, ge=0.0, le=5.0)
    rl_model_path: str | None = None
    rl_normalize_path: str | None = None
    event_buffer_size: int = 1000
    sim_default_controller: str = "lqr"


@lru_cache
def get_settings() -> Settings:
    return Settings()
