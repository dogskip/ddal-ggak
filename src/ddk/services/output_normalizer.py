"""OutputNormalizer service — Phase 3 (GEN-02).

Responsible for applying convention fixes to generated artifacts via a single LLM call.
Produces a NormalizationReport and a (potentially patched) GeneratedArtifactSet.

Key contract:
- Empty artifacts (files=[]) → short-circuit, 0 LLM calls, returns the SAME object (identity)
- One LLM call for non-empty artifacts
- drift_score_before from all convention_fixes; drift_score_after from unresolved_drift only
- System prompt starts with "Normalize" so FakeLLMAdapter routes to key "normalize"
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.normalization import ConventionFix, NormalizationReport
from ddk.models.repo import RepoProfile

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
- Respond with valid JSON only — no markdown fences, no commentary
"""


class _NormalizationLLMOutput(BaseModel):
    """Internal model for the LLM's normalization response."""

    convention_fixes: list[dict[str, Any]] = []
    unresolved_drift: list[str] = []
    patched_files: dict[str, str] = {}


class OutputNormalizer:
    """Applies LLM-driven convention normalization to a GeneratedArtifactSet."""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-haiku-20240307",
            temperature=0.0,
            max_tokens=2048,
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

        llm_output = await self._call_llm(artifacts, repo_profile)

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

        # Apply patched file content (if LLM returned any patches)
        patched = self._apply_patches(artifacts, llm_output.patched_files)

        return report, patched

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> _NormalizationLLMOutput:
        """Issue the LLM normalization call."""
        files_payload = [
            {"path": f.path, "content": f.content, "language": f.language}
            for f in artifacts.files
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
        try:
            data = json.loads(response.content)
            return _NormalizationLLMOutput(**data)
        except Exception:
            return _NormalizationLLMOutput()

    def _apply_patches(
        self,
        artifacts: GeneratedArtifactSet,
        patched_files: dict[str, str],
    ) -> GeneratedArtifactSet:
        """Return a new GeneratedArtifactSet with patched file contents applied."""
        if not patched_files:
            return artifacts

        updated_files: list[GeneratedFile] = []
        updated_file_map: dict[str, str] = dict(artifacts.file_map)

        for gf in artifacts.files:
            if gf.path in patched_files:
                new_content = patched_files[gf.path]
                updated_files.append(
                    GeneratedFile(
                        path=gf.path,
                        content=new_content,
                        language=gf.language,
                        source_node_id=gf.source_node_id,
                        is_new=gf.is_new,
                        original_content=gf.content,
                    )
                )
                updated_file_map[gf.path] = new_content
            else:
                updated_files.append(gf)

        return GeneratedArtifactSet(
            case_id=artifacts.case_id,
            files=updated_files,
            file_map=updated_file_map,
            generation_trace=artifacts.generation_trace,
            changed_paths=artifacts.changed_paths,
        )
