"""FakeCostTracker — always returns 0.0 cost. Tracks all recorded calls."""

from __future__ import annotations

from typing import Any


class FakeCostTracker:
    """Always returns 0.0 cost. Tracks all recorded calls."""

    def __init__(self) -> None:
        self.recorded_calls: list[dict[str, Any]] = []
        self.total_cost: float = 0.0

    def record_call(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        cost = 0.0  # Fake always returns 0
        self.recorded_calls.append(
            {
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
            }
        )
        self.total_cost += cost
        return cost

    def get_total_cost(self) -> float:
        return self.total_cost
