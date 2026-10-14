"""Anthropic Claude LLM adapter."""

from __future__ import annotations

import json
from typing import Any

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ddk.exceptions import (
    CostCapExceededError,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)
from ddk.models.config import DEFAULT_PRIMARY_MODEL

from .base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from .model_traits import estimate_cost, model_traits, output_budget
from .parsing import parse_llm_json

# Stop reasons that mean the reply ended before the model finished.
_CUT_OFF = ("max_tokens", "model_context_window_exceeded")


class ClaudeAdapter:
    """Anthropic Claude adapter implementing the LLMAdapter protocol."""

    def __init__(
        self,
        api_key: str,
        default_model: str = DEFAULT_PRIMARY_MODEL,
        cost_cap_usd: float = float("inf"),
        timeout_s: float = 120.0,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ClaudeAdapter requires a non-empty api_key. "
                "Set DDK_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) in the environment."
            )
        # Bound every call: the SDK default (10 min) is too long for a CLI workflow.
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)
        self._default_model = default_model
        self._cost_cap_usd = cost_cap_usd
        self._accumulated_cost: float = 0.0

    def reset_cost_tracking(self) -> None:
        """Reset the accumulated cost counter (e.g. between pipeline runs)."""
        self._accumulated_cost = 0.0

    def _check_cost_cap(self) -> None:
        """Raise CostCapExceededError if the cap has already been reached."""
        if self._accumulated_cost >= self._cost_cap_usd:
            raise CostCapExceededError(
                accumulated_usd=self._accumulated_cost,
                cap_usd=self._cost_cap_usd,
            )

    @retry(
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _messages_create(self, **kwargs: Any) -> anthropic.types.Message:
        """Stream one message to its end, retrying with backoff on 429 / 5xx errors.

        Streaming keeps the connection busy, so an answer that takes longer than the read timeout
        to write (large code, long thinking) is not cut off.
        """
        async with self._client.messages.stream(**kwargs) as stream:  # type: ignore[call-overload]
            return await stream.get_final_message()

    async def _invoke(self, **kwargs: Any) -> anthropic.types.Message:
        """Run the API call, mapping provider errors to the DDK LLM hierarchy."""
        try:
            return await self._messages_create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMAuthenticationError(str(exc)) from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMAuthenticationError(str(exc)) from exc
        except anthropic.RateLimitError as exc:  # retries exhausted
            raise LLMRateLimitError(str(exc)) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise LLMConnectionError(str(exc)) from exc
        except anthropic.NotFoundError as exc:
            raise LLMResponseError(
                f"Model '{kwargs.get('model', '')}' was not found or is not enabled for this API "
                f"key ({exc}). Set DDK_LLM_MODEL / DDK_LIGHT_MODEL to a model the key can use."
            ) from exc
        except anthropic.BadRequestError as exc:
            raise LLMResponseError(f"Provider rejected the request: {exc}") from exc
        except anthropic.APIError as exc:  # InternalServerError and other API errors
            raise LLMConnectionError(f"Provider API error: {exc}") from exc

    def _request(
        self, model: str, config: LLMCallConfig, system: str, rest: list[Any]
    ) -> dict[str, Any]:
        """The request fields every call shares, limited to what ``model`` accepts."""
        traits = model_traits(model)
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": output_budget(model, config.max_tokens, config.effort),
            "messages": rest,
        }
        if traits.sampling:
            kwargs["temperature"] = config.temperature
        if traits.effort and config.effort is not None:
            kwargs["output_config"] = {"effort": config.effort}
        if system:
            kwargs["system"] = system
        return kwargs

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        """Send messages to Claude and return a text response."""
        self._check_cost_cap()
        model = config.model or self._default_model
        system_prompt, anthropic_messages = _split_messages(messages)

        kwargs = self._request(model, config, system_prompt, anthropic_messages)
        response: anthropic.types.Message = await self._invoke(**kwargs)
        _raise_if_declined(response)
        return self._to_response(model, response, _extract_text(response))

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type[Any],
    ) -> LLMResponse:
        """Have Claude answer by calling a tool whose input schema is ``output_schema``.

        Models that accept it are forced to call the tool. The others reject a forced tool choice,
        so they are told to call it, and JSON written as plain text is accepted as well.
        """
        self._check_cost_cap()
        model = config.model or self._default_model
        system_prompt, anthropic_messages = _split_messages(messages)

        schema: dict[str, Any] = (
            output_schema.model_json_schema()  # type: ignore[union-attr]
            if hasattr(output_schema, "model_json_schema")
            else {}
        )
        tool_name = output_schema.__name__ if hasattr(output_schema, "__name__") else "output"

        forced = model_traits(model).forced_tool
        if not forced:
            ask = f"Return your answer by calling the {tool_name} tool once. Do not answer in text."
            system_prompt = f"{system_prompt}\n\n{ask}" if system_prompt else ask
        kwargs = self._request(model, config, system_prompt, anthropic_messages)
        kwargs["tools"] = [
            {
                "name": tool_name,
                "description": f"Output structured {tool_name} data",
                "input_schema": schema,
            }
        ]
        kwargs["tool_choice"] = {"type": "tool", "name": tool_name} if forced else {"type": "auto"}

        response: anthropic.types.Message = await self._invoke(**kwargs)
        _raise_if_declined(response)
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason in _CUT_OFF:
            raise LLMResponseError(
                f"The '{tool_name}' answer was cut off (stop_reason={stop_reason}); "
                "raise max_tokens or lower the effort."
            )
        content = _extract_tool_input(response, tool_name) or _extract_json_text(response)
        if content is None:
            raise LLMResponseError(
                f"Model returned no structured '{tool_name}' output "
                f"(no tool call and no JSON in the text, stop_reason={stop_reason})."
            )
        return self._to_response(model, response, content)

    def _to_response(
        self, model: str, response: anthropic.types.Message, content: str
    ) -> LLMResponse:
        usage = response.usage  # type: ignore[reportUnknownMemberType]
        input_tok = int(usage.input_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        output_tok = int(usage.output_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        cost = estimate_cost(model, input_tok, output_tok)
        self._accumulated_cost += cost
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            raw_response=response.model_dump(),  # type: ignore[arg-type]
            truncated=getattr(response, "stop_reason", None) in _CUT_OFF,
        )


def _split_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Separate system message from user/assistant messages, handling image blocks."""
    system = ""
    rest: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            system = msg.content
        elif msg.images:
            # Build multi-part content with image blocks first, then text
            content_parts: list[dict[str, Any]] = []
            for img_b64, media_type in msg.images:
                content_parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    }
                )
            content_parts.append({"type": "text", "text": msg.content})
            rest.append({"role": msg.role, "content": content_parts})
        else:
            rest.append({"role": msg.role, "content": msg.content})
    return system, rest


def _raise_if_declined(response: anthropic.types.Message) -> None:
    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMResponseError(
            "The model declined this request (stop_reason=refusal); "
            "change the input or retry with another model."
        )


def _extract_text(response: anthropic.types.Message) -> str:
    """The reply's text blocks joined; thinking and tool blocks are skipped."""
    return "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str)
    )


def _extract_tool_input(response: anthropic.types.Message, tool_name: str) -> str | None:
    """Return the JSON given to ``tool_name``, or None when the model did not call it."""
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return json.dumps(block.input, ensure_ascii=False)  # type: ignore[union-attr]
    return None


def _extract_json_text(response: anthropic.types.Message) -> str | None:
    """Return JSON written as plain text (fences and surrounding prose tolerated), else None."""
    text = _extract_text(response)
    if not text.strip():
        return None
    try:
        return json.dumps(parse_llm_json(text), ensure_ascii=False)
    except LLMResponseError:
        return None


# Verify the adapter satisfies the protocol at import time
_: LLMAdapter = ClaudeAdapter.__new__(ClaudeAdapter)  # type: ignore[assignment]
