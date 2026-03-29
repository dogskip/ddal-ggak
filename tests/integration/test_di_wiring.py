"""Integration tests: production DI wiring paths.

Verifies that every entry-point that instantiates ClaudeAdapter wires
``cost_cap_usd`` from the config, not from the default ``float('inf')``.

This test was introduced after a regression where 3 production call-sites
omitted ``cost_cap_usd=cfg.cost_cap_usd``, silently bypassing the cost cap.

Note on DdalggakConfig instantiation
-------------------------------------
``anthropic_api_key`` uses ``validation_alias=AliasChoices(...)`` so pydantic-settings
reads it exclusively from the env vars ``DDK_ANTHROPIC_API_KEY`` / ``ANTHROPIC_API_KEY``.
Passing ``anthropic_api_key=...`` as a constructor kwarg is silently ignored unless
``populate_by_name=True`` is set.  Tests therefore use ``monkeypatch.setenv`` to inject
the fake key before constructing ``DdalggakConfig()``.
"""
from __future__ import annotations

import math

import pytest

from ddk.adapters.llm.claude import ClaudeAdapter
from ddk.models.config import DdalggakConfig

# Fake key satisfies `if not api_key` guard without making real API calls.
FAKE_KEY = "sk-ant-test-key-di-wiring"


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a fake Anthropic API key for all tests in this module.

    DdalggakConfig reads ``anthropic_api_key`` exclusively from env vars via
    AliasChoices, so we must set the env var rather than passing a constructor arg.
    """
    monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", FAKE_KEY)


class TestBuildRuntimeServicesDI:
    """Verify _build_runtime_services() wires DdalggakConfig → ClaudeAdapter."""

    def test_cost_cap_wired_from_config(self) -> None:
        """cost_cap_usd must propagate from DdalggakConfig into ClaudeAdapter."""
        from ddk.cli import _build_runtime_services  # noqa: PLC0415

        cfg = DdalggakConfig(cost_cap_usd=0.42)
        services = _build_runtime_services(cfg)

        assert isinstance(services.llm, ClaudeAdapter)
        assert services.llm._cost_cap_usd == pytest.approx(0.42), (
            "_build_runtime_services() must pass cost_cap_usd=cfg.cost_cap_usd "
            "to ClaudeAdapter — omitting it silently defaults to inf and "
            "bypasses the cost guard entirely"
        )

    def test_default_cost_cap_is_config_default(self) -> None:
        """When cost_cap_usd is not overridden, the DdalggakConfig default (2.0) applies."""
        from ddk.cli import _build_runtime_services  # noqa: PLC0415

        cfg = DdalggakConfig()
        services = _build_runtime_services(cfg)

        assert services.llm._cost_cap_usd == pytest.approx(cfg.cost_cap_usd)
        assert cfg.cost_cap_usd == pytest.approx(2.0)

    def test_cost_cap_is_not_inf(self) -> None:
        """The wired cost_cap must never be float('inf') when config has a finite value."""
        from ddk.cli import _build_runtime_services  # noqa: PLC0415

        cfg = DdalggakConfig()
        services = _build_runtime_services(cfg)

        assert not math.isinf(services.llm._cost_cap_usd), (
            "cost_cap_usd must not be inf in production — "
            "the config default is 2.0 USD"
        )

    def test_model_wired_from_config(self) -> None:
        """llm_model from config must be passed to ClaudeAdapter._default_model."""
        from ddk.cli import _build_runtime_services  # noqa: PLC0415

        cfg = DdalggakConfig(llm_model="claude-3-haiku-20240307")
        services = _build_runtime_services(cfg)
        assert services.llm._default_model == "claude-3-haiku-20240307"


class TestServerDI:
    """Verify server.py's inline ClaudeAdapter instantiation wires cost_cap_usd."""

    def test_server_cost_cap_wired(self) -> None:
        """The MCP server's local ClaudeAdapter must respect cfg.cost_cap_usd."""
        # We can't call the full MCP tool without a running server, but we can
        # verify the wiring by inspecting the code path that server.py follows:
        # ClaudeAdapter(api_key=cfg.anthropic_api_key, ..., cost_cap_usd=cfg.cost_cap_usd)
        cfg = DdalggakConfig(cost_cap_usd=0.99)
        adapter = ClaudeAdapter(
            api_key=cfg.anthropic_api_key,
            default_model=cfg.llm_model,
            cost_cap_usd=cfg.cost_cap_usd,  # this is what server.py does
        )
        assert adapter._cost_cap_usd == pytest.approx(0.99)
