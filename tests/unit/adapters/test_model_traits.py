"""What each Claude model accepts in a request, and what a call costs."""

from __future__ import annotations

import pytest

from ddk.adapters.llm.model_traits import estimate_cost, model_traits, output_budget

_CURRENT = ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
_LEGACY_WITH_SAMPLING = [
    "claude-sonnet-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
    "claude-opus-4-5-20251101",
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
]


class TestRequestRules:
    @pytest.mark.parametrize("model", _CURRENT)
    def test_current_models_take_no_sampling_settings(self, model: str) -> None:
        assert model_traits(model).sampling is False

    @pytest.mark.parametrize("model", _LEGACY_WITH_SAMPLING)
    def test_older_models_still_take_temperature(self, model: str) -> None:
        assert model_traits(model).sampling is True

    @pytest.mark.parametrize("model", ["claude-opus-4-7", "claude-opus-4-8"])
    def test_sampling_settings_were_removed_from_opus_4_7_on(self, model: str) -> None:
        assert model_traits(model).sampling is False

    @pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5"])
    def test_these_models_reject_a_forced_tool_choice(self, model: str) -> None:
        assert model_traits(model).forced_tool is False

    @pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-4-6", "claude-opus-4-8"])
    def test_these_models_accept_a_forced_tool_choice(self, model: str) -> None:
        assert model_traits(model).forced_tool is True

    @pytest.mark.parametrize(
        "model", [*_CURRENT, "claude-sonnet-4-6", "claude-opus-4-5-20251101", "claude-opus-4-7"]
    )
    def test_effort_is_available(self, model: str) -> None:
        assert model_traits(model).effort is True

    @pytest.mark.parametrize(
        "model",
        ["claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929", "claude-3-haiku-20240307"],
    )
    def test_effort_is_not_sent_where_it_is_unsupported(self, model: str) -> None:
        assert model_traits(model).effort is False

    def test_dated_and_undated_ids_are_the_same_model(self) -> None:
        assert model_traits("claude-haiku-4-5") == model_traits("claude-haiku-4-5-20251001")
        assert model_traits("claude-3-5-haiku-latest") == model_traits("claude-3-5-haiku-20241022")

    def test_unknown_model_gets_only_what_every_model_accepts(self) -> None:
        traits = model_traits("claude-from-the-future")

        assert (traits.sampling, traits.forced_tool, traits.effort) == (False, False, False)


class TestPrices:
    @pytest.mark.parametrize(
        ("model", "usd"),
        [
            ("claude-fable-5-1", 60.0),
            ("claude-opus-5-5", 24.0),
            ("claude-sonnet-5-5", 12.0),
            ("claude-sonnet-4-6", 18.0),
            ("claude-haiku-4-5-20251001", 6.0),
            ("claude-opus-4-5-20251101", 30.0),
            ("claude-3-haiku-20240307", 1.5),
        ],
    )
    def test_one_million_tokens_each_way(self, model: str, usd: float) -> None:
        assert estimate_cost(model, 1_000_000, 1_000_000) == pytest.approx(usd)

    def test_haiku_5_5_short_prompt_uses_the_base_price(self) -> None:
        # 100,000 prompt tokens: $0.10/MTok in, $0.50/MTok out.
        assert estimate_cost("claude-haiku-5-5", 100_000, 1_000_000) == pytest.approx(0.51)

    def test_haiku_5_5_prompt_over_100k_tokens_costs_more(self) -> None:
        # $0.50/MTok in, $2.50/MTok out once the prompt passes 100,000 tokens.
        assert estimate_cost("claude-haiku-5-5", 100_001, 10_000) == pytest.approx(0.0750005)

    def test_unknown_model_is_priced_like_the_most_expensive_one(self) -> None:
        # A cost cap must not under-count what it cannot price.
        assert estimate_cost("claude-from-the-future", 1_000_000, 0) == pytest.approx(10.0)


class TestOutputBudget:
    def test_models_that_think_get_room_beyond_the_answer(self) -> None:
        assert output_budget("claude-sonnet-5-5", 4096, "low") > 4096

    def test_room_grows_with_effort(self) -> None:
        low, medium, high = (
            output_budget("claude-sonnet-5-5", 4096, e) for e in ("low", "medium", "high")
        )

        assert low < medium < high

    def test_unset_effort_means_the_model_default(self) -> None:
        assert output_budget("claude-sonnet-5-5", 4096, None) == output_budget(
            "claude-sonnet-5-5", 4096, "high"
        )
        assert output_budget("claude-haiku-5-5", 4096, None) == output_budget(
            "claude-haiku-5-5", 4096, "medium"
        )

    def test_models_that_do_not_think_keep_the_requested_limit(self) -> None:
        assert output_budget("claude-sonnet-4-6", 4096, "low") == 4096

    def test_never_asks_for_more_than_the_model_can_write(self) -> None:
        assert output_budget("claude-sonnet-5-5", 127_000, "max") == 128_000
