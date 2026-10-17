"""Verified-change CLI preserves the service result and requires explicit authority."""

from __future__ import annotations

import asyncio
import importlib
from uuid import UUID

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.public_contract import public_payload

runner = CliRunner()
CASE_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000002"
APPLY_ID = "00000000-0000-4000-8000-000000000003"


class Service:
    def __init__(self):
        self.calls = []
        self.result = {
            "schema_version": "verified-change/1",
            "case_id": CASE_ID,
            "run_id": RUN_ID,
            "decision": "ready",
            "assurance": "isolated",
            "actions": [],
        }
        self.error = None

    def import_case(self, case_path, inputs_dir=None):
        self.calls.append(("import_case", {"case_path": case_path, "inputs_dir": inputs_dir}))
        return {"case_id": CASE_ID, "assurance_required": "trusted-local"}

    async def verify(self, case_id, **kwargs):
        self.calls.append(("verify", {"case_id": case_id, **kwargs}))
        print("service progress")
        return self._result()

    def status(self, run_id):
        self.calls.append(("status", {"run_id": run_id}))
        return self._result()

    def export(self, run_id, destination, **kwargs):
        self.calls.append(("export", {"run_id": run_id, "destination": destination, **kwargs}))
        return self._result()

    def apply(self, **kwargs):
        self.calls.append(("apply", kwargs))
        return self._result()

    def recover(self, apply_id, **kwargs):
        self.calls.append(("recover", {"apply_id": apply_id, **kwargs}))
        return self._result()

    def _result(self):
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def service(monkeypatch):
    service = Service()
    verified = importlib.import_module("ddk.cli.verified")
    monkeypatch.setattr(verified, "_service", lambda repository: service)
    return service


def verify_args(tmp_path):
    return [
        "change",
        "verify",
        "--repo",
        str(tmp_path),
        "--case-id",
        CASE_ID,
        "--baseline",
        str(tmp_path / "baseline"),
        "--candidate",
        str(tmp_path / "candidate"),
        "--run-id",
        RUN_ID,
        "--json",
    ]


def apply_args(tmp_path):
    return [
        "change",
        "apply",
        "--repo",
        str(tmp_path),
        "--apply-id",
        APPLY_ID,
        "--case-id",
        CASE_ID,
        "--run-id",
        RUN_ID,
        "--run-sha256",
        "a" * 64,
        "--changes-sha256",
        "b" * 64,
        "--confirm-local-storage",
        "--confirm-quiescence",
        "--json",
    ]


def test_change_commands_have_their_own_namespace():
    result = runner.invoke(app, ["change", "--help"])
    assert result.exit_code == 0, result.output
    for command in ("verify", "status", "export", "apply", "recover"):
        assert command in result.output
    assert "repair" in result.output


def test_verify_forwards_explicit_inputs_and_keeps_json_clean(tmp_path, service):
    inputs = tmp_path / "project-inputs.json"
    requirements = tmp_path / "requirements.json"
    inputs.write_text('{"package.json":"package.json"}')
    requirements.write_text('{"src/App.tsx":["R1"]}')

    result = runner.invoke(
        app,
        verify_args(tmp_path)
        + [
            "--project-inputs",
            str(inputs),
            "--change-requirements",
            str(requirements),
        ],
    )

    assert result.exit_code == 0, result.output
    assert public_payload(result.stdout) == service.result
    assert "service progress" in result.stderr
    assert service.calls == [
        (
            "verify",
            {
                "case_id": CASE_ID,
                "baseline": tmp_path / "baseline",
                "candidate": tmp_path / "candidate",
                "run_id": RUN_ID,
                "project_inputs": {"package.json": "package.json"},
                "change_requirements": {"src/App.tsx": ["R1"]},
                "trusted_local_approved": False,
            },
        )
    ]


def test_case_import_never_grants_host_execution_authority(tmp_path, service):
    case = tmp_path / "case.json"
    case.write_text("{}")
    inputs = tmp_path / "inputs"
    args = verify_args(tmp_path)
    offset = args.index("--case-id")
    args[offset : offset + 2] = ["--case", str(case), "--inputs", str(inputs)]

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    assert service.calls[0] == ("import_case", {"case_path": case, "inputs_dir": inputs})
    assert service.calls[1][1]["trusted_local_approved"] is False


def test_host_execution_requires_explicit_cli_selection(tmp_path, service):
    result = runner.invoke(app, verify_args(tmp_path) + ["--trusted-local"])
    assert result.exit_code == 0, result.output
    assert service.calls[0][1]["trusted_local_approved"] is True


def test_trusted_local_help_discloses_host_authority_and_no_os_isolation():
    from typer.main import get_command

    from ddk.i18n import ENGLISH

    command = get_command(app).commands["change"].commands["verify"]
    parameter = next(p for p in command.params if "--trusted-local" in p.opts)
    text = ENGLISH.get(parameter.help, parameter.help)
    assert "host permissions" in text
    assert "no OS isolation" in text


def test_verify_generates_a_uuid_when_run_id_is_omitted(tmp_path, service):
    args = verify_args(tmp_path)
    offset = args.index("--run-id")
    del args[offset : offset + 2]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert UUID(service.calls[0][1]["run_id"]).version == 4


@pytest.mark.parametrize("selection", ["neither", "both", "inputs-with-id"])
def test_invalid_case_selection_stops_before_service(tmp_path, service, selection):
    args = verify_args(tmp_path)
    if selection == "neither":
        offset = args.index("--case-id")
        del args[offset : offset + 2]
    elif selection == "both":
        args += ["--case", str(tmp_path / "case.json")]
    else:
        args += ["--inputs", str(tmp_path / "inputs")]

    result = runner.invoke(app, args)

    assert result.exit_code == 3, result.output
    assert public_payload(result.stdout)["error"]["code"]
    assert service.calls == []


@pytest.mark.parametrize(
    "document",
    [
        b'{"a":"x","a":"y"}',
        b'{"a":NaN}',
        b"[]",
        b'{"a":4}',
        b'{"a":"' + b"x" * (2 * 1024 * 1024) + b'"}',
        b'{"a":' + b"[" * 34 + b"0" + b"]" * 34 + b"}",
    ],
)
def test_invalid_project_input_json_is_rejected_before_import(tmp_path, service, document):
    document_path = tmp_path / "inputs.json"
    document_path.write_bytes(document)
    result = runner.invoke(app, verify_args(tmp_path) + ["--project-inputs", str(document_path)])
    assert result.exit_code == 3, result.output
    assert public_payload(result.stdout)["error"]["code"]
    assert service.calls == []


@pytest.mark.parametrize("document", ['{"src/App.tsx":"R1"}', '{"src/App.tsx":[4]}'])
def test_change_requirements_must_map_paths_to_string_arrays(tmp_path, service, document):
    path = tmp_path / "requirements.json"
    path.write_text(document)
    result = runner.invoke(app, verify_args(tmp_path) + ["--change-requirements", str(path)])
    assert result.exit_code == 3, result.output
    assert service.calls == []


@pytest.mark.parametrize(
    ("decision", "exit_code"),
    [
        ("ready", 0),
        ("blocked", 1),
        ("manual-review", 1),
        (None, 3),
    ],
)
def test_status_decision_controls_exit_code_without_restarting(
    tmp_path, service, decision, exit_code
):
    service.result["decision"] = decision
    result = runner.invoke(
        app, ["change", "status", "--repo", str(tmp_path), "--run-id", RUN_ID, "--json"]
    )
    assert result.exit_code == exit_code, result.output
    assert public_payload(result.stdout) == service.result
    assert service.calls == [("status", {"run_id": RUN_ID})]


def test_human_output_contains_only_decision_assurance_identifiers_and_actions(tmp_path, service):
    service.result.update(
        {
            "private_payload": "hidden-value",
            "actions": [
                {
                    "code": "review_required",
                    "target": "src/App.tsx",
                    "message": "Review the change.",
                    "retryable": False,
                }
            ],
        }
    )
    result = runner.invoke(app, ["change", "status", "--run-id", RUN_ID])
    assert result.exit_code == 0, result.output
    for expected in ("ready", "isolated", CASE_ID, RUN_ID, "review_required", "Review the change."):
        assert expected in result.stdout
    assert "hidden-value" not in result.stdout
    assert "private_payload" not in result.stdout


@pytest.mark.parametrize("sensitive", [False, True])
def test_export_requires_explicit_sensitive_selection(tmp_path, service, sensitive):
    destination = tmp_path / "export"
    args = ["change", "export", "--run-id", RUN_ID, "--destination", str(destination), "--json"]
    if sensitive:
        args += ["--include-sensitive"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert service.calls == [
        (
            "export",
            {
                "run_id": RUN_ID,
                "destination": destination,
                "include_sensitive": sensitive,
            },
        )
    ]


def test_apply_forwards_confirmations_and_defaults_to_isolated(tmp_path, service):
    service.result = {
        "apply_id": APPLY_ID,
        "case_id": CASE_ID,
        "run_id": RUN_ID,
        "state": "applied",
        "actions": [],
    }
    result = runner.invoke(app, apply_args(tmp_path))
    assert result.exit_code == 0, result.output
    assert public_payload(result.stdout) == service.result
    assert service.calls == [
        (
            "apply",
            {
                "apply_id": APPLY_ID,
                "case_id": CASE_ID,
                "run_id": RUN_ID,
                "run_sha256": "a" * 64,
                "changes_sha256": "b" * 64,
                "quiescence_confirmed": True,
                "local_storage_confirmed": True,
                "required_assurance": "isolated",
            },
        )
    ]


@pytest.mark.parametrize("flag", ["--confirm-local-storage", "--confirm-quiescence"])
def test_apply_without_confirmation_never_calls_service(tmp_path, service, flag):
    args = apply_args(tmp_path)
    args.remove(flag)
    result = runner.invoke(app, args)
    assert result.exit_code == 3, result.output
    assert service.calls == []


@pytest.mark.parametrize("flag", ["--case-id", "--run-id", "--run-sha256", "--changes-sha256"])
def test_apply_requires_explicit_identity_and_hashes(tmp_path, service, flag):
    args = apply_args(tmp_path)
    offset = args.index(flag)
    del args[offset : offset + 2]
    result = runner.invoke(app, args)
    assert result.exit_code == 2, result.output
    assert service.calls == []


@pytest.mark.parametrize(
    ("state", "exit_code"),
    [
        ("rolled_back", 0),
        ("conflict", 1),
        ("unknown", 1),
        ("applying", 3),
    ],
)
def test_recovery_requires_all_confirmations_and_reports_result(
    tmp_path, service, state, exit_code
):
    service.result = {"apply_id": APPLY_ID, "state": state, "actions": []}
    result = runner.invoke(
        app,
        [
            "change",
            "recover",
            "--apply-id",
            APPLY_ID,
            "--confirm-local-storage",
            "--confirm-same-host",
            "--confirm-quiescence",
            "--json",
        ],
    )
    assert result.exit_code == exit_code, result.output
    assert public_payload(result.stdout) == service.result
    assert service.calls == [
        (
            "recover",
            {
                "apply_id": APPLY_ID,
                "local_storage_confirmed": True,
                "same_host_confirmed": True,
                "quiescence_confirmed": True,
            },
        )
    ]


@pytest.mark.parametrize(
    "flag",
    [
        "--confirm-local-storage",
        "--confirm-same-host",
        "--confirm-quiescence",
    ],
)
def test_recovery_without_confirmation_never_calls_service(tmp_path, service, flag):
    args = [
        "change",
        "recover",
        "--apply-id",
        APPLY_ID,
        "--confirm-local-storage",
        "--confirm-same-host",
        "--confirm-quiescence",
        "--json",
    ]
    args.remove(flag)
    result = runner.invoke(app, args)
    assert result.exit_code == 3, result.output
    assert service.calls == []


@pytest.mark.parametrize(
    "error", [ValueError("request_conflict"), FileNotFoundError("missing_run")]
)
def test_service_input_errors_are_structured_and_exit_three(tmp_path, service, error):
    service.error = error
    result = runner.invoke(app, verify_args(tmp_path))
    assert result.exit_code == 3, result.output
    assert str(error) in public_payload(result.stdout)["error"]["code"]


@pytest.mark.parametrize(
    "code",
    [
        "isolation_unavailable",
        "environment_gap",
        "ambiguous_baseline",
        "baseline_mismatch",
        "ambiguous_change_requirements",
        "invalid_change_requirements",
    ],
)
def test_registered_unavailable_and_input_categories_preserve_original_record(
    tmp_path, service, code
):
    service.result.update(decision="blocked", actions=[{"code": code}])
    result = runner.invoke(app, verify_args(tmp_path))
    expected = 4 if code in {"isolation_unavailable", "environment_gap"} else 3
    assert result.exit_code == expected, result.output
    assert public_payload(result.stdout) == service.result


@pytest.mark.parametrize("code", ["required_check_failed", "baseline_failed", "protected_change"])
def test_real_check_or_candidate_policy_failure_stays_exit_one(tmp_path, service, code):
    service.result.update(decision="blocked", actions=[{"code": code}])
    result = runner.invoke(app, verify_args(tmp_path))
    assert result.exit_code == 1, result.output
    assert public_payload(result.stdout) == service.result


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (asyncio.CancelledError(), 130),
        (KeyboardInterrupt(), 130),
        (ValueError("invalid_request"), 3),
    ],
)
@pytest.mark.parametrize("explicit_id", [False, True])
def test_verify_error_retains_selected_run_id_for_status(
    tmp_path, service, error, exit_code, explicit_id
):
    service.error = error
    args = verify_args(tmp_path)
    if not explicit_id:
        offset = args.index("--run-id")
        del args[offset : offset + 2]
    result = runner.invoke(app, args)
    assert result.exit_code == exit_code, result.output
    payload = public_payload(result.stdout)
    assert payload["run_id"] == service.calls[0][1]["run_id"]
    assert UUID(payload["run_id"]).version == 4
    assert payload["case_id"] == CASE_ID


def test_status_input_error_retains_requested_run_id(service):
    service.error = FileNotFoundError("missing_run")
    result = runner.invoke(app, ["change", "status", "--run-id", RUN_ID, "--json"])
    assert result.exit_code == 3, result.output
    assert public_payload(result.stdout)["run_id"] == RUN_ID


def test_saved_cancelled_run_keeps_cancellation_exit_code(service):
    service.result.update(status="cancelled", decision=None)
    result = runner.invoke(app, ["change", "status", "--run-id", RUN_ID, "--json"])
    assert result.exit_code == 130, result.output
    assert public_payload(result.stdout) == service.result


def test_blocked_workflow_cannot_exit_zero_with_a_ready_verification(service):
    service.result.update(status="blocked", actions=[{"code": "working_tree_changed"}])
    result = runner.invoke(app, ["change", "status", "--run-id", RUN_ID, "--json"])
    assert result.exit_code == 1, result.output
    assert public_payload(result.stdout) == service.result
