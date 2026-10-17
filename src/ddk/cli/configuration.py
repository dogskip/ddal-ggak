"""Inspect repository-scoped configuration without revealing credentials."""

from pathlib import Path

import typer

from ddk.i18n import t
from ddk.models.config import observe_settings

from .app import app
from .common import console, is_secret_setting, print_json, state
from .contract import CommandFailureError

config_app = typer.Typer(help=t("설정 값과 적용 출처를 확인합니다."))
app.add_typer(config_app, name="config")


@config_app.command("list", help=t("비밀 값을 숨기고 설정과 출처를 조회합니다."))
def list_settings(
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    try:
        config, sources = observe_settings(repo, state.flag_overrides)
    except (ValueError, OSError) as error:
        raise CommandFailureError("configuration", "invalid_settings") from error
    settings = {
        name: {"value": "***" if is_secret_setting(name) else value, "source": sources[name]}
        for name, value in config.model_dump(mode="json").items()
    }
    payload = {"settings": settings}
    if as_json:
        print_json(payload)
    else:
        console.print(payload)
