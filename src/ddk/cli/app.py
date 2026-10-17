"""The Typer application and its global options."""

from __future__ import annotations

import typer
from typer._click.core import ParameterSource

from ddk.i18n import t

from .common import load_settings, state
from .contract import ContractGroup

app = typer.Typer(
    name="ddk",
    cls=ContractGroup,
    help=t(
        "딸깍 — 디자인 이미지에서 코드를 생성하고, 실제 브라우저로 화면을 비교하고, "
        "자동 수정과 증거 기반 판정을 거칩니다."
    ),
    add_completion=False,
    rich_markup_mode="rich",
)
design_app = typer.Typer(help=t("Design Studio — 아이디어에서 설계 문서를 생성합니다"))
app.add_typer(design_app, name="design")


def _show_version(value: bool) -> bool:
    if value:
        from .workspace import version

        version()
        raise typer.Exit(0)
    return value


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_show_version, is_eager=True, help=t("설치 버전을 출력합니다.")
    ),
    log_level: str = typer.Option("INFO", envvar="DDK_LOG_LEVEL", help=t("로그 수준")),
) -> None:
    """Global options shared by every command."""
    from ddk.logging.setup import configure_logging  # noqa: PLC0415

    state.flag_overrides = (
        {"log_level": log_level}
        if ctx.get_parameter_source("log_level") == ParameterSource.COMMANDLINE
        else {}
    )
    load_settings()
    configure_logging(level=state.config.log_level if state.config else log_level)


def cli_main() -> None:
    """Console-script entry point."""
    app()
