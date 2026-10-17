from __future__ import annotations

import tomllib
from collections.abc import Callable
from contextvars import ContextVar
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import AliasChoices, Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from ddk.models.verified_change import Record
from ddk.security.file_access import read_regular

DEFAULT_PRIMARY_MODEL = "claude-sonnet-5-5"
DEFAULT_LIGHT_MODEL = "claude-haiku-5-5"
DEFAULT_SANDBOX_MODE = "tempdir"


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    # Reserved for forward-compatible config parsing; runtime adapters are not shipped yet.
    OPENAI = "openai"
    FAKE = "fake"


class DdalggakConfig(BaseSettings):
    model_config = {
        "env_prefix": "DDK_",
        "env_file": ".env",
        "extra": "ignore",
        "populate_by_name": True,
    }

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
    llm_model: str = DEFAULT_PRIMARY_MODEL
    light_model: str = DEFAULT_LIGHT_MODEL
    cost_cap_usd: float = Field(default=2.0, ge=0, allow_inf_nan=False)
    sandbox_mode: str = DEFAULT_SANDBOX_MODE
    sandbox_timeout_seconds: int = 300
    install_dependencies: bool = False
    playwright_browser: str = "chromium"
    log_level: str = "INFO"
    log_format: str = "text"
    log_redact: bool = True
    visual_check: bool = True
    ssim_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    max_mismatch_ratio: float = Field(default=0.03, ge=0.0, le=1.0)
    chromium_path: str = ""
    reproducibility_mode: str = "best_effort"
    benchmark_seed: int = 42
    record_all_calls: bool = True
    max_retry_attempts: int = Field(default=3, ge=1, le=10)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        dotenv = getattr(dotenv_settings, "env_file", ".env")
        path = Path(dotenv) if isinstance(dotenv, str | Path) else Path(".env")
        return (
            _NormalizedSource(settings_cls, init_settings, "flag"),
            _NormalizedSource(settings_cls, env_settings, "environment"),
            _NormalizedSource(settings_cls, dotenv_settings, "dotenv"),
            _NormalizedSource(
                settings_cls, lambda: _toml_settings(path.parent / "ddk.toml"), "toml"
            ),
        )


_ORIGINS: ContextVar[dict[str, str] | None] = ContextVar("ddk_settings_origins", default=None)


class _NormalizedSource(PydanticBaseSettingsSource):
    def __init__(
        self, settings_cls: type[BaseSettings], source: Callable[[], Record], label: str
    ) -> None:
        super().__init__(settings_cls)
        self.source = source
        self.label = label

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[object, str, bool]:
        return self().get(field_name), field_name, False

    def __call__(self) -> Record:
        raw = self.source()
        normalized: Record = {}
        for name, field in self.settings_cls.model_fields.items():
            alias = field.validation_alias
            keys = (
                [alias]
                if isinstance(alias, str)
                else [p for p in alias.choices if isinstance(p, str)]
                if isinstance(alias, AliasChoices)
                else []
            )
            for key in [*keys, name]:
                if key in raw:
                    normalized[name] = raw[key]
                    origins = _ORIGINS.get()
                    if origins is not None:
                        origins.setdefault(name, self.label)
                    break
        return normalized


def _toml_settings(path: Path) -> Record:
    try:
        payload = read_regular(path, 2 * 1024**2)
    except FileNotFoundError:
        return {}
    settings = tomllib.loads(payload.decode("utf-8")).get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("invalid_settings_table")
    return cast(Record, settings)


def observe_settings(
    repository: Path, overrides: Record | None = None
) -> tuple[DdalggakConfig, dict[str, str]]:
    origins: dict[str, str] = {}
    token = _ORIGINS.set(origins)
    try:
        arguments: Record = {"_env_file": repository / ".env", **(overrides or {})}
        config = DdalggakConfig(**arguments)
    finally:
        _ORIGINS.reset(token)
    return config, {name: origins.get(name, "default") for name in type(config).model_fields}
