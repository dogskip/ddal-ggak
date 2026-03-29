"""OutputNormalizer — GeneratedArtifactSet → NormalizationReport + patched artifacts (CODEGEN-02)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models._base import DDKBaseModel
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.normalization import ConventionFix, NormalizationReport
from ddk.models.repo import RepoProfile

# KEY: starts with "Normalize" → FakeLLM key="normalize".
# Must not start with "you", "generate", "analyze", or "senior" (all taken).
_SYSTEM_PROMPT = """Normalize convention violations for repository code.

Review generated code and output a list of convention fixes.

Focus on:
1. Component naming: PascalCase vs kebab-case per NamingRules
2. File placement: components in correct directory per FileLayoutRules
3. Import ordering: external libraries before internal
4. Design token usage: replace hardcoded colors/spacing with token references
5. Primitive reuse: use existing components if functionally equivalent

Do NOT change business logic or component structure.
Do NOT fix TypeScript errors.

## Response Format
Output structured JSON with a convention_fixes array, unresolved_drift array, and patched_files dict."""


class _NormalizationLLMOutput(DDKBaseModel):
    """LLM output schema for OutputNormalizer. Internal use only."""

    convention_fixes: list[ConventionFix] = Field(default_factory=list)
    unresolved_drift: list[str] = Field(default_factory=list)
    patched_files: dict[str, str] = Field(default_factory=dict)
    # patched_files: path → patched content (LLM applies fixes inline)


class OutputNormalizer:
    """Normalizes generated code to match RepoProfile conventions (CODEGEN-02).

    LLM-based normalization (haiku) per 16-prompt-design.md §6.
    NOT rule-based AST — the LLM understands context (e.g., same color for bg vs text).
    Model: claude-3-haiku-20240307, temperature=0.0.
    """

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-haiku-20240307",
            temperature=0.0,
            max_tokens=2048,
        )

    async def normalize(
        self,
        artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> tuple[NormalizationReport, GeneratedArtifactSet]:
        """Normalize generated artifacts against repo conventions.

        Returns:
            Tuple of (NormalizationReport with drift scores, patched GeneratedArtifactSet).

        Empty artifacts (files=[]) returns an empty NormalizationReport and unchanged
        artifacts without making any LLM call.
        """
        if not artifacts.files:
            report = NormalizationReport(
                case_id=artifacts.case_id,
                convention_fixes=[],
                drift_score_before=0.0,
                drift_score_after=0.0,
                unresolved_drift=[],
            )
            return report, artifacts

        # Build file listing for LLM context (cap at 10 files for token budget)
        files_summary = "\n\n".join(
            f"### {f.path}\n```typescript\n{f.content[:800]}\n```"
            for f in artifacts.files[:10]
        )

        user_content = (
            f"Normalize these generated files against the repository conventions.\n\n"
            f"## Repository Profile\n"
            f"Framework: {repo_profile.framework}\n"
            f"{repo_profile.model_dump_json(indent=2)[:1500]}\n\n"
            f"## Generated Files\n{files_summary}\n\n"
            f"Output a JSON object with convention_fixes, unresolved_drift, and patched_files."
        )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response: LLMResponse = await self._llm.complete_structured(
            messages, self._config, output_schema=_NormalizationLLMOutput
        )

        data: dict[str, Any] = json.loads(response.content)
        llm_output = _NormalizationLLMOutput.model_validate(data)

        # Compute drift scores using design-spec formula (12-data-models.md)
        drift_score_before = NormalizationReport.compute_drift_score(llm_output.convention_fixes)

        # drift_score_after reflects only fixes the LLM could not resolve
        unresolved_score_fixes: list[ConventionFix] = [
            f for f in llm_output.convention_fixes
            if f.description in llm_output.unresolved_drift
        ]
        drift_score_after = NormalizationReport.compute_drift_score(unresolved_score_fixes)

        report = NormalizationReport(
            case_id=artifacts.case_id,
            convention_fixes=llm_output.convention_fixes,
            drift_score_before=drift_score_before,
            drift_score_after=drift_score_after,
            unresolved_drift=llm_output.unresolved_drift,
        )

        # Apply patched content from LLM if provided
        if llm_output.patched_files:
            patched_file_list = []
            for f in artifacts.files:
                if f.path in llm_output.patched_files:
                    patched_file_list.append(
                        f.model_copy(update={"content": llm_output.patched_files[f.path]})
                    )
                else:
                    patched_file_list.append(f)
            patched_file_map = {pf.path: pf.content for pf in patched_file_list}
            patched_artifacts = artifacts.model_copy(
                update={"files": patched_file_list, "file_map": patched_file_map}
            )
        else:
            patched_artifacts = artifacts

        return report, patched_artifacts
