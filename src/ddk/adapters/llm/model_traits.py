"""What each Claude model accepts in a request, and what a call costs.

Checked against platform.claude.com/docs (models, effort, pricing) on 2026-10-14. A model that
is not listed gets only the settings every model accepts, and the highest known price.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import cache

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 128_000
_DEFAULT_EFFORT_ROOM = 16_384

# Extra output tokens that cover thinking, by effort. The model may think for more or less.
_THINKING_ROOM = {"low": 2_048, "medium": 8_192, "high": 16_384, "xhigh": 32_768, "max": 65_536}


@dataclass(frozen=True)
class LongPromptPrice:
    """Higher per-million-token prices that apply once a prompt is longer than ``over_tokens``."""

    over_tokens: int
    input_usd: float
    output_usd: float


@dataclass(frozen=True)
class ModelTraits:
    input_usd: float  # per million input tokens
    output_usd: float  # per million output tokens
    sampling: bool = False  # accepts temperature
    forced_tool: bool = False  # accepts tool_choice "any" or "tool"
    effort: bool = False  # accepts output_config.effort
    default_effort: str | None = None  # set when the model thinks unless told otherwise
    long_prompt: LongPromptPrice | None = None


def _older(input_usd: float, output_usd: float, *, effort: bool = False) -> ModelTraits:
    """A model from before Opus 4.7: temperature and a forced tool both work."""
    return ModelTraits(input_usd, output_usd, sampling=True, forced_tool=True, effort=effort)


def _thinking(
    input_usd: float,
    output_usd: float,
    *,
    default_effort: str,
    forced_tool: bool = False,
    long_prompt: LongPromptPrice | None = None,
) -> ModelTraits:
    """A 5-generation model: no sampling settings, and it thinks before answering by default."""
    return ModelTraits(
        input_usd,
        output_usd,
        forced_tool=forced_tool,
        effort=True,
        default_effort=default_effort,
        long_prompt=long_prompt,
    )


_FAMILIES: dict[str, ModelTraits] = {
    "claude-fable-5-1": _thinking(10, 50, default_effort="high"),
    "claude-fable-5": _thinking(10, 50, default_effort="high"),
    "claude-mythos-5-1": _thinking(10, 50, default_effort="high"),
    "claude-mythos-5": _thinking(10, 50, default_effort="high"),
    "claude-opus-5-5": _thinking(4, 20, default_effort="medium"),
    "claude-opus-5": _thinking(5, 25, default_effort="high"),
    "claude-sonnet-5-5": _thinking(2, 10, default_effort="high"),
    "claude-sonnet-5": _thinking(2, 10, default_effort="high"),
    "claude-haiku-5-5": _thinking(
        0.10,
        0.50,
        default_effort="medium",
        forced_tool=True,
        long_prompt=LongPromptPrice(100_000, 0.50, 2.50),
    ),
    "claude-opus-4-8": ModelTraits(5, 25, forced_tool=True, effort=True),
    "claude-opus-4-7": ModelTraits(5, 25, forced_tool=True, effort=True),
    "claude-opus-4-6": _older(5, 25, effort=True),
    "claude-opus-4-5": _older(5, 25, effort=True),
    "claude-opus-4-1": _older(15, 75),
    "claude-opus-4": _older(15, 75),
    "claude-sonnet-4-6": _older(3, 15, effort=True),
    "claude-sonnet-4-5": _older(3, 15),
    "claude-sonnet-4": _older(3, 15),
    "claude-haiku-4-5": _older(1, 5),
    "claude-3-7-sonnet": _older(3, 15),
    "claude-3-5-sonnet": _older(3, 15),
    "claude-3-5-haiku": _older(0.8, 4),
    "claude-3-haiku": _older(0.25, 1.25),
    "claude-3-opus": _older(15, 75),
}

# The highest known price: a cost cap must not under-count a model it cannot price.
_UNKNOWN = ModelTraits(10, 50)

_SNAPSHOT_OR_ALIAS = re.compile(r"-(?:\d{8}|latest)$")


def known_model_names() -> frozenset[str]:
    """Explicit model names with verified request traits; aliases are excluded."""
    return frozenset(_FAMILIES)


@cache
def model_traits(model: str) -> ModelTraits:
    """Request rules and prices for ``model`` (dated snapshots and ``-latest`` aliases included)."""
    traits = _FAMILIES.get(_SNAPSHOT_OR_ALIAS.sub("", model.strip().lower()))
    if traits is None:
        logger.warning(
            "Unknown model %r: sending only the settings every model accepts and "
            "pricing it at $%g/$%g per million tokens.",
            model,
            _UNKNOWN.input_usd,
            _UNKNOWN.output_usd,
        )
        return _UNKNOWN
    return traits


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Dollar cost of one call."""
    traits = model_traits(model)
    input_usd, output_usd = traits.input_usd, traits.output_usd
    long_prompt = traits.long_prompt
    if long_prompt is not None and input_tokens > long_prompt.over_tokens:
        input_usd, output_usd = long_prompt.input_usd, long_prompt.output_usd
    return (input_tokens * input_usd + output_tokens * output_usd) / 1_000_000


def output_budget(model: str, max_tokens: int, effort: str | None) -> int:
    """``max_tokens`` to send: the answer's size plus room for thinking on models that think.

    Thinking counts toward ``max_tokens``, so the bare answer size can end the reply in mid-thought.
    """
    default_effort = model_traits(model).default_effort
    if default_effort is None:
        return max_tokens
    room = _THINKING_ROOM.get(effort or default_effort, _DEFAULT_EFFORT_ROOM)
    return max(max_tokens, min(max_tokens + room, _MAX_OUTPUT_TOKENS))
