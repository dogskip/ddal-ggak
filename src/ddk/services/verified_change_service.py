"""Shared user operations for fixed verification, review and owned application."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Mapping, Sequence
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ddk.models.verified_change import Record, canonical_json, decode_json, validate_structure
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import normalize_source_path
from ddk.services.artifact_applier import ArtifactApplier
from ddk.services.durable_files import atomic_write, ensure_directory
from ddk.services.verified_budget import VerifiedPrice
from ddk.services.verified_change_engine import Evaluator, VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_repair import RepairProvider, VerifiedRepairEngine


class VerifiedChangeService:
    """Expose the same authority to CLI and MCP without provider construction."""

    def __init__(self, repository: Path, *, evaluator: Evaluator | None = None) -> None:
        self.store = VerifiedChangeStore(repository, create=False)
        self._evaluator = evaluator

    def import_case(self, case_path: Path, inputs_dir: Path | None = None) -> Record:
        record = decode_json(read_regular(case_path, 2 * 1024**2))
        validate_structure(record)
        if record["record_type"] != "case":
            raise ValueError("case_record_required")
        directory = inputs_dir if inputs_dir is not None else case_path.parent / "inputs"
        payloads: dict[str, bytes] = {}
        total = 0
        for item in record["inputs"]:
            path = directory / normalize_source_path(item["path"])
            payload = read_regular(path, record["limits"]["max_file_bytes"])
            total += len(payload)
            if total > record["limits"]["max_artifact_bytes"]:
                raise ValueError("input_size_limit")
            payloads[item["path"]] = payload
        self.store.initialize()
        return self.store.publish_case(record, payloads)

    async def verify(
        self,
        case_id: str,
        *,
        baseline: Path | None = None,
        candidate: Path | None = None,
        run_id: str,
        project_inputs: Mapping[str, str] | None = None,
        change_requirements: Mapping[str, Sequence[str]] | None = None,
        trusted_local_approved: bool = False,
        git_base: str | None = None,
    ) -> Record:
        case = self.store.case(case_id)
        evaluator = self._approved_evaluator(case, trusted_local_approved)
        self.store.initialize()
        return await VerifiedChangeEngine(self.store, evaluator).verify(
            case_id,
            baseline=baseline,
            candidate=candidate,
            run_id=run_id,
            project_inputs=project_inputs,
            change_requirements=change_requirements,
            git_base=git_base,
        )

    def _approved_evaluator(self, case: Record, approved: bool) -> Evaluator:
        if approved and case["assurance_required"] != "trusted-local":
            raise ValueError("assurance_mismatch")
        if not approved and case["assurance_required"] == "trusted-local":
            raise ValueError("trusted_local_confirmation_required")
        if self._evaluator is not None:
            return self._evaluator
        from ddk.adapters.verified_evaluator import VerifiedEvaluator  # noqa: PLC0415

        return VerifiedEvaluator(trusted_local_approved=approved)

    async def repair(
        self,
        source_run_id: str,
        *,
        baseline: Path,
        candidate: Path,
        run_id: str,
        price: VerifiedPrice,
        input_limit: int,
        output_limit: int,
        provider: RepairProvider,
        provider_approved: bool = False,
        trusted_local_approved: bool = False,
        project_inputs: Mapping[str, str] | None = None,
    ) -> Record:
        """Repair only after explicit provider and execution grants."""
        if not provider_approved:
            raise ValueError("provider_confirmation_required")
        if (
            type(input_limit) is not int
            or input_limit < 1
            or type(output_limit) is not int
            or not 1 <= output_limit <= 128_000
        ):
            raise ValueError("provider_token_limit_invalid")
        source = self.store.run(source_run_id)
        case = self.store.case(source["case_id"])
        evaluator = self._approved_evaluator(case, trusted_local_approved)
        return await VerifiedRepairEngine(self.store, evaluator, provider).repair(
            source_run_id,
            baseline=baseline,
            candidate=candidate,
            run_id=run_id,
            price=price,
            input_limit=input_limit,
            output_limit=output_limit,
            project_inputs=project_inputs,
        )

    def status(self, run_id: str) -> Record:
        return self.store.status(run_id)

    def export(self, run_id: str, destination: Path, *, include_sensitive: bool = False) -> Record:
        run = self.store.run(run_id)
        case = self.store.case(run["case_id"])
        report = {
            "case_id": run["case_id"],
            "run_id": run_id,
            "status": run["status"],
            "decision": run["decision"],
            "assurance": run["assurance"],
            "checks": [
                {
                    key: result[key]
                    for key in (
                        ("check_id", "phase", "status", "reason_code")
                        if include_sensitive
                        else ("check_id", "phase", "status")
                    )
                }
                for result in run["results"]
            ],
            "changes": [
                {key: change[key] for key in ("path", "action", "before_sha256", "after_sha256")}
                for change in run["changes"]
            ],
            "actions": [{"code": action["code"]} for action in run["actions"]],
            "private_export": include_sensitive,
        }
        included: list[str] = []
        buffer = io.BytesIO()
        size = 0
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("report.json", canonical_json(report))
            for artifact in run["artifacts"]:
                if not include_sensitive and (
                    artifact["sensitive"] or not artifact["public_export_allowed"]
                ):
                    continue
                payload = read_regular(
                    self.store.path_for("run", run_id) / artifact["path"],
                    case["limits"]["max_artifact_bytes"],
                )
                if (
                    len(payload) != artifact["size_bytes"]
                    or hashlib.sha256(payload).hexdigest() != artifact["sha256"]
                ):
                    raise ValueError("export_artifact_changed")
                size += len(payload)
                if size > case["limits"]["max_artifact_bytes"]:
                    raise ValueError("export_size_limit")
                archive.writestr(artifact["path"], payload)
                included.append(artifact["artifact_id"])
        content = buffer.getvalue()
        if len(content) > case["limits"]["max_artifact_bytes"]:
            raise ValueError("export_size_limit")
        ensure_directory(destination.parent)
        atomic_write(destination, content, exclusive=True)
        return {
            "run_id": run_id,
            "destination": str(destination),
            "included_artifacts": included,
            "private_export": include_sensitive,
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def apply(
        self,
        *,
        apply_id: str,
        case_id: str,
        run_id: str,
        run_sha256: str,
        changes_sha256: str,
        quiescence_confirmed: bool = False,
        local_storage_confirmed: bool = False,
        required_assurance: str = "isolated",
        target_run_id: str | None = None,
    ) -> Record:
        return ArtifactApplier().apply_run(
            self.store,
            apply_id=apply_id,
            case_id=case_id,
            run_id=run_id,
            run_sha256=run_sha256,
            changes_sha256=changes_sha256,
            quiescence_confirmed=quiescence_confirmed,
            local_storage_confirmed=local_storage_confirmed,
            required_assurance=required_assurance,
            target_run_id=target_run_id,
        )

    def recover(
        self,
        apply_id: str,
        *,
        local_storage_confirmed: bool = False,
        same_host_confirmed: bool = False,
        quiescence_confirmed: bool = False,
    ) -> Record:
        return ArtifactApplier().recover(
            self.store,
            apply_id,
            local_storage_confirmed=local_storage_confirmed,
            same_host_confirmed=same_host_confirmed,
            quiescence_confirmed=quiescence_confirmed,
        )
