"""Global and command version interfaces use the installed distribution version."""

from importlib.metadata import version

from typer.testing import CliRunner

from ddk.cli import app


def test_global_version_is_eager_and_matches_the_version_command():
    runner = CliRunner()
    for args in [["--version"], ["version"]]:
        result = runner.invoke(app, args, env={"DDK_COST_CAP_USD": "broken"})
        assert result.exit_code == 0, result.output
        assert result.stdout.strip() == f"ddk {version('ddalggak')}"
