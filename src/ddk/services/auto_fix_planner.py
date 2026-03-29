"""AutoFixPlanner — 9-rule hybrid patch planner. VALID-04."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.validation import FailureRecord

# ─────────────────────────────────────────────
# Deterministic rule functions (R-01 ~ R-08)
# ─────────────────────────────────────────────


def r01_remove_unused_import(content: str, symbol: str) -> str:
    """R-01 (FT-LINT-001): Remove import line containing unused symbol."""
    lines = content.splitlines(keepends=True)
    escaped = re.escape(symbol)
    result = [
        line for line in lines if not re.search(rf"\bimport\b.*\b{escaped}\b.*\bfrom\b", line)
    ]
    return "".join(result)


def r02_eslint_fix_command(file_path: str) -> list[str]:
    """R-02 (FT-LINT-002/003): Return eslint --fix command for file."""
    return ["npx", "eslint", "--fix", file_path]


def r03_add_any_annotation(content: str, symbol: str) -> str:
    """R-03 (FT-TYPE-002): Add ': any' type annotation to parameter/variable."""
    escaped = re.escape(symbol)
    pattern = rf"\b({escaped})\s*(?=[,\)=])"
    return re.sub(pattern, r"\1: any", content, count=1)


def r04_add_cast(content: str, expression: str, target_type: str) -> str:
    """R-04 (FT-TYPE-001/003): Wrap expression with 'as unknown as T' cast."""
    escaped = re.escape(expression)
    replacement = f"({expression} as unknown as {target_type})"
    return re.sub(escaped, replacement, content, count=1)


def r05_add_dependency(pkg_json_content: str, package_name: str, version: str = "latest") -> str:
    """R-05 (FT-BUILD-003): Add package to package.json dependencies."""
    data: dict[str, Any] = json.loads(pkg_json_content)
    data.setdefault("dependencies", {})[package_name] = version
    return json.dumps(data, indent=2)


def r06_fix_relative_import(content: str, wrong_path: str, correct_path: str) -> str:
    """R-06 (FT-BUILD-001): Replace wrong import path with correct relative path."""
    escaped = re.escape(wrong_path)
    pattern = rf"(from\s+['\"]){escaped}(['\"])"
    replacement = rf"\g<1>{correct_path}\g<2>"
    return re.sub(pattern, replacement, content)


def r07_add_optional_chaining(content: str, expr: str) -> str:
    """R-07 (FT-RUNTIME-002): Replace foo.bar.baz with foo?.bar?.baz."""
    parts = expr.split(".")
    if len(parts) < 2:
        return content
    chained = "?.".join(parts)
    return content.replace(expr, chained, 1)


def r08_add_await(content: str, call_expr: str) -> str:
    """R-08 (FT-ASYNC-002): Prepend 'await' to async call expression."""
    return content.replace(call_expr, f"await {call_expr}", 1)


# ─────────────────────────────────────────────
# Taxonomy → rule mapping
# ─────────────────────────────────────────────

_TAXONOMY_TO_RULE: dict[str, str] = {
    "FT-LINT-001": "R-01",
    "FT-LINT-002": "R-02",
    "FT-LINT-003": "R-02",
    "FT-TYPE-002": "R-03",
    "FT-TYPE-001": "R-04",
    "FT-TYPE-003": "R-04",
    "FT-BUILD-003": "R-05",
    "FT-BUILD-001": "R-06",
    "FT-RUNTIME-002": "R-07",
    "FT-ASYNC-002": "R-08",
    "FT-BUILD-002": "R-09",
    "FT-RUNTIME-001": "R-09",
}

_AUTOFIX_SYSTEM_PROMPT = """\
Autofix the following TypeScript/JavaScript source file.
The file has the following error(s). Regenerate the file fixing ONLY the listed errors.
Respond with the complete fixed file content only — no markdown fences.
"""

# Rule ID to function mapping for deterministic rules
_RULE_FUNCTIONS: dict[str, Any] = {
    "R-01": r01_remove_unused_import,
    "R-03": r03_add_any_annotation,
    "R-04": r04_add_cast,
    "R-05": r05_add_dependency,
    "R-06": r06_fix_relative_import,
    "R-07": r07_add_optional_chaining,
    "R-08": r08_add_await,
}


def _apply_rule_to_content(rule_id: str, content: str, failure: FailureRecord) -> str:
    """Apply a deterministic rule function to file content and return the modified content."""
    if rule_id == "R-01":
        match = re.search(r"['\"](\w+)['\"]", failure.message)
        symbol = match.group(1) if match else "Unknown"
        return r01_remove_unused_import(content, symbol)
    if rule_id == "R-03":
        match = re.search(r"['\"](\w+)['\"]", failure.message)
        symbol = match.group(1) if match else "x"
        return r03_add_any_annotation(content, symbol)
    if rule_id == "R-04":
        expr = failure.message.split("'")[1] if "'" in failure.message else "expr"
        return r04_add_cast(content, expr, "any")
    if rule_id == "R-05":
        match = re.search(r"['\"]([^'\"]+)['\"]", failure.message)
        pkg = match.group(1) if match else "unknown-pkg"
        return r05_add_dependency(content, pkg)
    if rule_id == "R-06":
        parts = failure.message.split("'")
        wrong = parts[1] if len(parts) > 1 else ""
        correct = parts[3] if len(parts) > 3 else wrong
        return r06_fix_relative_import(content, wrong, correct)
    if rule_id == "R-07":
        match = re.search(r"(\w+(?:\.\w+)+)", failure.message)
        expr = match.group(1) if match else ""
        return r07_add_optional_chaining(content, expr)
    if rule_id == "R-08":
        match = re.search(r"(\w+\([^)]*\))", failure.message)
        call_expr = match.group(1) if match else ""
        return r08_add_await(content, call_expr)
    return content


def _update_artifacts(
    artifacts: GeneratedArtifactSet,
    file_path: str,
    new_content: str,
) -> GeneratedArtifactSet:
    """Return a new GeneratedArtifactSet with the specified file's content updated."""
    updated_files: list[GeneratedFile] = []
    for f in artifacts.files:
        if f.path == file_path:
            updated_files.append(f.model_copy(update={"content": new_content}))
        else:
            updated_files.append(f)
    return artifacts.model_copy(update={"files": updated_files})


class AutoFixPlanner:
    """9-rule hybrid patch planner. R-01~R-08 deterministic, R-09 LLM. VALID-04."""

    def __init__(self, llm: LLMAdapter) -> None:
        self.llm = llm

    async def plan_and_apply(
        self,
        failures: list[FailureRecord],
        artifacts: Any,
        case_id: str,
        attempt_number: int,
    ) -> tuple[FixAttempt, Any]:
        """Select and apply the best matching rule for the first/most severe failure."""
        start = time.monotonic()

        if not failures:
            return (
                FixAttempt(
                    attempt_number=attempt_number,
                    case_id=case_id,
                    trigger_failures=[],
                    rule_id="none",
                    files_patched=[],
                    patch_description="No failures to fix",
                    success=False,
                ),
                artifacts,
            )

        primary = failures[0]
        rule_id = _TAXONOMY_TO_RULE.get(primary.taxonomy_id, "none")

        files_patched: list[str] = []
        patch_description = f"No applicable rule for {primary.taxonomy_id}"
        updated_artifacts = artifacts

        if rule_id == "R-09":
            file_content = self._find_file_content(artifacts, primary.file_path)
            messages = [
                Message(role="system", content=_AUTOFIX_SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=(
                        f"File: {primary.file_path or 'unknown'}\n\n"
                        f"Errors:\n{primary.raw_output}\n\n"
                        f"Current content:\n{file_content}"
                    ),
                ),
            ]
            config = LLMCallConfig(
                model="claude-3-5-haiku-20241022",
                max_tokens=4096,
                temperature=0.0,
            )
            response = await self.llm.complete(messages, config)
            if (
                response.content
                and primary.file_path
                and isinstance(artifacts, GeneratedArtifactSet)
            ):
                updated_artifacts = _update_artifacts(
                    artifacts, primary.file_path, response.content
                )
            files_patched = [primary.file_path] if primary.file_path else []
            patch_description = f"R-09: LLM regeneration for {primary.taxonomy_id}"

        elif rule_id == "R-02":
            files_patched = [primary.file_path] if primary.file_path else []
            patch_description = f"{rule_id}: eslint --fix for {primary.file_path}"

        elif (
            rule_id in _RULE_FUNCTIONS
            and primary.file_path
            and isinstance(artifacts, GeneratedArtifactSet)
        ):
            file_content = self._find_file_content(artifacts, primary.file_path)
            new_content = _apply_rule_to_content(rule_id, file_content, primary)
            if new_content != file_content:
                updated_artifacts = _update_artifacts(artifacts, primary.file_path, new_content)
            match = re.search(r"['\"](\w+)['\"]", primary.message)
            symbol = match.group(1) if match else ""
            files_patched = [primary.file_path]
            patch_description = f"{rule_id}: Applied to {primary.file_path}"
            if rule_id == "R-01":
                patch_description = f"R-01: Remove unused import '{symbol}'"

        elif rule_id != "none":
            files_patched = [primary.file_path] if primary.file_path else []
            patch_description = f"{rule_id}: Applied to {primary.file_path}"

        duration_ms = int((time.monotonic() - start) * 1000)
        attempt = FixAttempt(
            attempt_number=attempt_number,
            case_id=case_id,
            trigger_failures=[primary.id],
            rule_id=rule_id,
            files_patched=files_patched,
            patch_description=patch_description,
            success=rule_id != "none",
            remaining_failures=[f.id for f in failures[1:]],
            duration_ms=duration_ms,
        )
        return attempt, updated_artifacts

    @staticmethod
    def _find_file_content(artifacts: Any, file_path: str | None) -> str:
        """Find and return file content from artifacts, or empty string."""
        if not file_path or not isinstance(artifacts, GeneratedArtifactSet):
            return ""
        for f in artifacts.files:
            if f.path == file_path:
                return f.content
        return ""
