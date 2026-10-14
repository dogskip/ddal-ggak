"""DDK runtime exceptions.

These are Python exceptions (not Pydantic models) raised by the core adapters
and services when operations cannot be completed safely.
"""

from __future__ import annotations


class DirtyWorkingTreeError(RuntimeError):
    """Raised when ``rollback_to()`` is called on a repo with uncommitted changes.

    A rollback via ``git reset --hard`` would permanently destroy any modifications
    that have not been committed. Callers must either commit/stash those changes
    or pass ``force=True`` to explicitly opt-in to the destructive behaviour.

    Attributes:
        repo_path: Absolute path to the repository that has a dirty tree.
        modified: Files with unstaged modifications.
        staged: Files with staged (but uncommitted) changes.
        untracked: Files git does not track yet (``git clean`` would delete them).
    """

    def __init__(
        self,
        repo_path: object,
        modified: list[str],
        staged: list[str],
        untracked: list[str] | None = None,
    ) -> None:
        self.repo_path = repo_path
        self.modified = modified
        self.staged = staged
        self.untracked = untracked or []
        summary = ", ".join(modified + staged + self.untracked) or "unknown"
        super().__init__(
            f"Dirty working tree at {repo_path}: uncommitted files [{summary}]. "
            "Commit or stash changes before rolling back, "
            "or pass force=True to discard them."
        )


class CostCapExceededError(RuntimeError):
    """Raised when the accumulated LLM cost exceeds the configured cap.

    Prevents runaway spend by halting the pipeline before issuing further API
    calls once ``DdalggakConfig.cost_cap_usd`` has been reached.

    Attributes:
        accumulated_usd: How much was spent before the cap was hit.
        cap_usd: The configured spending ceiling.
    """

    def __init__(self, accumulated_usd: float, cap_usd: float) -> None:
        self.accumulated_usd = accumulated_usd
        self.cap_usd = cap_usd
        super().__init__(
            f"LLM cost cap exceeded: accumulated ${accumulated_usd:.4f} USD "
            f">= cap ${cap_usd:.4f} USD. "
            "Increase DdalggakConfig.cost_cap_usd or reduce pipeline scope."
        )


class LLMError(RuntimeError):
    """Base class for failures at the LLM provider boundary.

    Adapters map opaque provider SDK errors to this hierarchy so the pipeline and
    CLI can present actionable messages and choose terminal states deterministically.
    """


class LLMAuthenticationError(LLMError):
    """The provider rejected the credentials (bad / missing / revoked API key)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "LLM authentication failed — check DDK_ANTHROPIC_API_KEY (or "
            "ANTHROPIC_API_KEY)." + (f" Provider said: {detail}" if detail else "")
        )


class LLMConnectionError(LLMError):
    """A network problem or timeout prevented reaching the provider."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "Could not reach the LLM provider (network error or timeout)."
            + (f" {detail}" if detail else "")
        )


class LLMRateLimitError(LLMError):
    """Rate limited and retries were exhausted."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "LLM rate limit exceeded after retries — back off and retry later."
            + (f" {detail}" if detail else "")
        )


class LLMResponseError(LLMError):
    """The provider returned an unusable response (empty / malformed / rejected)."""


class GenerationError(RuntimeError):
    """The model's answer for a planned node could not be turned into usable files."""
