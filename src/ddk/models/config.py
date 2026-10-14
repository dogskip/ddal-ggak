from __future__ import annotations

from enum import StrEnum

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings

DEFAULT_PRIMARY_MODEL = "claude-sonnet-5-5"
DEFAULT_LIGHT_MODEL = "claude-haiku-5-5"
DEFAULT_SANDBOX_MODE = "tempdir"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    FAKE = "fake"


class DdalggakConfig(BaseSettings):
    model_config = {"env_prefix": "DDK_", "env_file": ".env", "extra": "ignore"}

    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    # API keys: DDK_* prefix takes priority; plain env vars (ANTHROPIC_API_KEY,
    # OPENAI_API_KEY) are accepted as fallback so existing shell configs just work.
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DDK_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DDK_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    llm_model: str = "claude-3-5-sonnet-20241022"
    light_model: str = "claude-3-haiku-20240307"
    cost_cap_usd: float = 2.0
    sandbox_mode: str = "worktree"
    sandbox_timeout_seconds: int = 300
    playwright_browser: str = "chromium"
    log_level: str = "INFO"
    log_format: str = "text"
    log_redact: bool = True
    case_dir: str = ".ddk"
    ssim_threshold: float = 0.92
    pixel_diff_threshold: float = 0.05
    reproducibility_mode: str = "best_effort"
    benchmark_seed: int = 42
    record_all_calls: bool = True
    max_retry_attempts: int = Field(default=3, ge=1, le=10)
