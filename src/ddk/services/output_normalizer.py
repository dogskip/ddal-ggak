"""OutputNormalizer service — Phase 3 (GEN-02).

Responsible for applying convention fixes to generated artifacts via a single LLM call.
Produces a NormalizationReport and a (potentially patched) GeneratedArtifactSet.

Key contract:
- Empty artifacts (files=[]) → short-circuit, 0 LLM calls, returns the SAME object (identity)
- One LLM call for non-empty artifacts
- drift_score_before from all convention_fixes; drift_score_after from unresolved_drift only
- A cut-off or unreadable answer leaves the files as they were and is named in ``skipped_rules``
- A patch is applied only for a generated file, and not when it is empty, shrinks the file to under
  half, or adds a placeholder comment such as ``// ... rest unchanged``
- System prompt starts with "Normalize" so FakeLLMAdapter routes to key "normalize"
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.adapters.llm.parsing import parse_llm_json
from ddk.models.config import DEFAULT_LIGHT_MODEL
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.normalization import ConventionFix, NormalizationReport
from ddk.models.repo import RepoProfile

logger = logging.getLogger(__name__)

_MAX_TOKENS = 16_384
_MIN_KEPT_SHARE = 0.5
# A comment that says code was left out, e.g. "// ... rest of the component unchanged".
_ELISION = re.compile(
    r"^\s*(?://|/\*|\{/\*|\*)[^\n]*(?:\.\.\.|…|rest of|unchanged|existing code|omitted)",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# System prompt — MUST start with "Normalize" so FakeLLMAdapter routes to
# the "normalize" key via:  msg.content.split()[0].lower() == "normalize"
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
Normalize the following generated React/TypeScript source files to match
the repository's coding conventions.

You will receive a JSON object with generated files and repo conventions.
Respond with a JSON object matching this exact schema:
{
  "convention_fixes": [
    {
      "fix_type": "naming",
      "file_path": "<path>",
      "rule_id": "<rule id, e.g. NAMING-001>",
      "description": "<human-readable description>",
      "before_snippet": "<code before fix>",
      "after_snippet": "<code after fix>",
      "severity": "must-fix | should-fix | nice-to-have",
      "before": "<original text>",
      "after": "<normalized text>"
    }
  ],
  "unresolved_drift": ["<rule_id that could not be auto-fixed>", ...],
  "patched_files": {
    "<file_path>": "<full patched content>"
  }
}

Rules:
- Apply all auto-fixable violations and list them in convention_fixes
- Leave issues that need human judgement in unresolved_drift
- Every patched file must be complete: never abbreviate it with placeholders such as
  "// ... rest unchanged"
- Respond with valid JSON only — no markdown fences, no commentary
"""


class _NormalizationLLMOutput(BaseModel):
    """Internal model for the LLM's normalization response."""

    convention_fixes: list[dict[str, Any]] = []
    unresolved_drift: list[str] = []
    patched_files: dict[str, str] = {}


class OutputNormalizer:
    """Applies LLM-driven convention normalization to a GeneratedArtifactSet."""

    def __init__(self, llm: LLMAdapter, model: str = DEFAULT_LIGHT_MODEL) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model=model,
            temperature=0.0,
            max_tokens=_MAX_TOKENS,
            effort="low",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def normalize(
        self,
        artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> tuple[NormalizationReport, GeneratedArtifactSet]:
        """Normalize generated artifacts against repo conventions.

        Short-circuits when artifacts.files is empty (no LLM call).

        Args:
            artifacts: The generated files to normalize.
            repo_profile: Repository conventions to check against.

        Returns:
            A 2-tuple of (NormalizationReport, patched GeneratedArtifactSet).
            When empty, returns (report, artifacts) where patched *is* the input object.
        """
        if not artifacts.files:
            # Short-circuit: return identity of the same artifacts object
            return (
                NormalizationReport(
                    case_id=artifacts.case_id,
                    convention_fixes=[],
                    drift_score_before=0.0,
                    drift_score_after=0.0,
                    unresolved_drift=[],
                ),
                artifacts,  # identity: same object reference
            )

        llm_output, skipped_rules = await self._call_llm(artifacts, repo_profile)

        # Parse convention fixes into ConventionFix model instances
        convention_fixes: list[ConventionFix] = []
        for fix_dict in llm_output.convention_fixes:
            try:
                convention_fixes.append(ConventionFix(**fix_dict))
            except ValidationError:
                continue

        drift_score_before = NormalizationReport.compute_drift_score(convention_fixes)

        # Unresolved drift score uses only unresolved fixes (those that couldn't be patched)
        unresolved_fixes = [f for f in convention_fixes if f.rule_id in llm_output.unresolved_drift]
        drift_score_after = NormalizationReport.compute_drift_score(unresolved_fixes)

        report = NormalizationReport(
            case_id=artifacts.case_id,
            convention_fixes=convention_fixes,
            drift_score_before=drift_score_before,
            drift_score_after=drift_score_after,
            unresolved_drift=llm_output.unresolved_drift,
        )

        patched, modified, rejected = self._apply_patches(artifacts, llm_output.patched_files)
        report.files_modified = modified
        report.skipped_rules = [*skipped_rules, *rejected]
        return report, patched

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> tuple[_NormalizationLLMOutput, list[str]]:
        """Issue the LLM normalization call; an unusable answer becomes "nothing to apply"."""
        files_payload = [
            {"path": f.path, "content": f.content, "language": f.language} for f in artifacts.files
        ]
        user_content = json.dumps(
            {
                "files": files_payload,
                "repo_framework": repo_profile.framework,
                "conventions": getattr(repo_profile, "conventions", {}),
            },
            ensure_ascii=False,
        )
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]
        response = await self._llm.complete(messages, self._config)
        if response.truncated:
            logger.warning("Normalization answer was cut off at %s tokens", _MAX_TOKENS)
            return _NormalizationLLMOutput(), ["normalization-truncated"]
        try:
            data = parse_llm_json(response.content)
            return _NormalizationLLMOutput(**data), []
        except Exception:  # noqa: BLE001
            logger.warning("Normalization LLM response parsing failed", exc_info=True)
            return _NormalizationLLMOutput(), ["normalization-unparseable"]

    def _apply_patches(
        self,
        artifacts: GeneratedArtifactSet,
        patched_files: dict[str, str],
    ) -> tuple[GeneratedArtifactSet, list[str], list[str]]:
        """Apply the sound patches; returns the new set, the modified paths and the rejections."""
        generated = {f.path: f for f in artifacts.files}
        accepted: dict[str, str] = {}
        rejected: list[str] = []
        for path, content in patched_files.items():
            original = generated.get(path)
            if original is None:
                rejected.append(f"patch-rejected:{path}:unknown-file")
            elif content == original.content:
                continue
            elif (problem := _patch_problem(original.content, content)) is not None:
                rejected.append(f"patch-rejected:{path}:{problem}")
            else:
                accepted[path] = content
        if not accepted:
            return artifacts, [], rejected

        files = [
            f.model_copy(update={"content": accepted[f.path]}) if f.path in accepted else f
            for f in artifacts.files
        ]
        patched = artifacts.model_copy(
            update={"files": files, "file_map": {**artifacts.file_map, **accepted}}
        )
        return patched, list(accepted), rejected


def _patch_problem(original: str, patched: str) -> str | None:
    if not patched.strip():
        return "empty"
    if len(patched) < len(original) * _MIN_KEPT_SHARE:
        return "shrunk"
    if len(_ELISION.findall(patched)) > len(_ELISION.findall(original)):
        return "elided"
    return None
