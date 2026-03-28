"""Design Studio writer — 생성된 문서를 design-package/ 디렉토리에 저장한다."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .generator import GeneratedDocument, GenerationResult
from .interviewer import InterviewResult


class DesignWriter:
    """design-package/ 디렉토리에 생성된 문서를 저장한다."""

    def __init__(self, output_dir: Path | str) -> None:
        self._output_dir = Path(output_dir)

    def write(self, result: GenerationResult, interview: InterviewResult) -> Path:
        """모든 생성 문서를 디스크에 저장하고 manifest를 반환한다.

        Args:
            result: 생성된 문서 목록
            interview: 인터뷰 결과 (manifest에 포함)

        Returns:
            design-package/ 디렉토리 경로
        """
        pkg_dir = self._output_dir / "design-package"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        for doc in result.documents:
            _write_document(pkg_dir, doc)

        if result.errors:
            _write_errors(pkg_dir, result.errors)

        manifest_path = _write_manifest(pkg_dir, result, interview)
        _write_readme(pkg_dir, result, interview)

        return manifest_path.parent

    def document_count(self, result: GenerationResult) -> int:
        return len(result.documents)


def _write_document(pkg_dir: Path, doc: GeneratedDocument) -> None:
    (pkg_dir / doc.filename).write_text(doc.content, encoding="utf-8")


def _write_errors(pkg_dir: Path, errors: dict[str, str]) -> None:
    lines = ["# 생성 오류\n"]
    for key, msg in errors.items():
        lines.append(f"## {key}\n```\n{msg}\n```\n")
    (pkg_dir / "ERRORS.md").write_text("\n".join(lines), encoding="utf-8")


def _write_manifest(
    pkg_dir: Path,
    result: GenerationResult,
    interview: InterviewResult,
) -> Path:
    manifest = {
        "schema_version": "1.0",
        "project_name": interview.project_name,
        "original_idea": interview.original_idea,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_cost_usd": round(result.total_cost_usd, 6),
        "documents": [
            {"key": d.key, "filename": d.filename, "cost_usd": round(d.cost_usd, 6)}
            for d in result.documents
        ],
        "errors": result.errors,
        "requirements": interview.extracted_requirements,
    }
    path = pkg_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_readme(
    pkg_dir: Path,
    result: GenerationResult,
    interview: InterviewResult,
) -> None:
    lines = [
        f"# {interview.project_name} — Design Package",
        "",
        f"> {interview.original_idea}",
        "",
        f"Generated at: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Total LLM cost: ${result.total_cost_usd:.4f} USD",
        "",
        "## Documents",
        "",
    ]
    for doc in result.documents:
        lines.append(f"- [{doc.filename}]({doc.filename})")

    if result.errors:
        lines += ["", "## ⚠️ Generation Errors", ""]
        for key in result.errors:
            lines.append(f"- {key}: failed (see ERRORS.md)")

    (pkg_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
