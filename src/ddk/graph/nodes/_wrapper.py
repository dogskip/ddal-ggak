"""Error boundary wrapper for LangGraph nodes — INFRA-04.

Usage::

    from ddk.graph.nodes._wrapper import node_wrapper

    workflow.add_node("my_node", node_wrapper(real_node_fn))
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.config import CONFIG_KEY_RUNTIME


def node_wrapper(
    node_fn: Callable[..., Any],
) -> Callable[..., Any]:
    """Return an async error-boundary wrapper around a LangGraph node function.

    The returned coroutine:
    - Extracts the ServiceContainer from LangGraph's RunnableConfig (context_schema DI)
      and forwards it as a ``context`` kwarg so node functions can access it uniformly
      whether called directly in tests or via the compiled graph.
    - Catches OS/permission/timeout errors and returns a safe error state so the graph
      can route to ``manual-review-required`` instead of crashing.

    Args:
        node_fn: The real async node function to wrap.

    Returns:
        An async callable with the same signature as ``node_fn``.
    """

    async def _wrapped(
        state: dict[str, Any],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Extract ServiceContainer from LangGraph runtime config (context_schema injection).
        # Falls back to any ``context`` already in **kwargs (direct unit-test calls).
        if "context" not in kwargs and config is not None:
            runtime = config.get("configurable", {}).get(CONFIG_KEY_RUNTIME)
            if runtime is not None:
                kwargs["context"] = runtime.context

        try:
            return await node_fn(state, **kwargs)  # type: ignore[no-any-return]
        except (OSError, PermissionError, TimeoutError) as exc:
            return {
                "terminal_state": "manual-review-required",
                "error_message": f"OS/timeout error in node: {exc}",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "terminal_state": "manual-review-required",
                "error_message": f"Unexpected error: {type(exc).__name__}: {exc}",
            }

    return _wrapped
