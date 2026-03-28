"""Integration tests for PreflightDoctor — runs against the real environment."""

from __future__ import annotations

from ddk.preflight.doctor import PreflightDoctor


class TestPreflightDoctorIntegration:
    """Tests run against the actual dev environment so they may show 'warn' or 'pass'
    for some checks depending on what's installed, but they must never crash.
    """

    def test_run_checks_returns_list(self) -> None:
        results = PreflightDoctor().run_checks()
        assert isinstance(results, list)
        assert len(results) == 5

    def test_all_results_have_required_keys(self) -> None:
        results = PreflightDoctor().run_checks()
        for r in results:
            assert "name" in r
            assert "status" in r
            assert "detail" in r
            assert "critical" in r

    def test_status_values_are_valid(self) -> None:
        results = PreflightDoctor().run_checks()
        valid_statuses = {"pass", "warn", "fail"}
        for r in results:
            assert r["status"] in valid_statuses, (
                f"Check '{r['name']}' has invalid status: {r['status']!r}"
            )

    def test_python_check_passes_in_dev_env(self) -> None:
        """Dev environment must run Python 3.12+."""
        results = PreflightDoctor().run_checks()
        python_result = next(r for r in results if "Python" in r["name"])
        assert python_result["status"] == "pass", (
            f"Python check failed: {python_result['detail']}"
        )

    def test_uv_check_passes_in_dev_env(self) -> None:
        """uv must be on PATH in the dev environment."""
        results = PreflightDoctor().run_checks()
        uv_result = next(r for r in results if "uv" in r["name"])
        assert uv_result["status"] == "pass", (
            f"uv not found: {uv_result['detail']}"
        )

    def test_git_check_present(self) -> None:
        """git check result must be present (pass or warn — never crash)."""
        results = PreflightDoctor().run_checks()
        git_result = next(r for r in results if "git" in r["name"].lower())
        assert git_result["status"] in {"pass", "warn"}, (
            f"git check returned fail in dev env: {git_result['detail']}"
        )

    def test_critical_field_is_bool(self) -> None:
        results = PreflightDoctor().run_checks()
        for r in results:
            assert isinstance(r["critical"], bool)
