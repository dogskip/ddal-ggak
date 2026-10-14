"""AutoFixPlanner — repairs generated files from real diagnostics. VALID-04.

Two deterministic, behaviour-preserving fixes run first:
- R-01 removes an unused import specifier.
- R-06 points a wrong relative import at the one generated file that matches.

Everything else goes to the model (R-09), one call per file with *all* of that file's
diagnostics, and the answer is vetted before it is kept: no empty or truncated file,
no new ``any`` / ``@ts-ignore`` / ``eslint-disable`` just to make the checker quiet.

R-02..R-05, R-07 and R-08 stay as pure helpers but are no longer applied automatically:
they mask errors (``any``, ``as unknown as``), add unreviewed dependencies, or guess
runtime semantics from a regex.

A ``FixAttempt`` reports only what changed; an attempt that changed nothing is not a success.
"""

from __future__ import annotations

import json
import posixpath
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.config import DEFAULT_LIGHT_MODEL
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.validation import FailureRecord
from ddk.models.visual import VisualRegressionReport
from ddk.security.repo_paths import (
    UnsafeRepositoryPathError,
    ensure_distinct_paths,
    normalize_change_path,
    resolve_change_path,
)
from ddk.services.file_blocks import FILE_HEADER, language_of, strip_fence
from ddk.services.images import encode_for_model

_MAX_FILES_PER_ATTEMPT = 4
_MAX_CONSUMER_TARGETS = 2
_MAX_CONTEXT_ERRORS = 10
_MIN_KEPT_RATIO = 0.4
_MIN_LENGTH_FOR_RATIO_CHECK = 200
_REPAIR_MAX_TOKENS = 16_384
_MAX_VISUAL_TARGETS = 2
_UI_SUFFIXES = (".css", ".scss", ".tsx", ".jsx", ".html", ".vue", ".svelte")
_ENTRY_STEMS = frozenset({"app", "index", "main", "page", "layout"})

_SILENCERS = ("@ts-ignore", "@ts-expect-error", "@ts-nocheck", "eslint-disable")
_ANY_ESCAPE = re.compile(r":\s*any\b|\bas\s+any\b|\bas\s+unknown\s+as\b|<any>")

_AUTOFIX_SYSTEM_PROMPT = """\
Autofix a generated React/TypeScript source file so that the project builds, type-checks \
and lints cleanly.

Rules:
- Fix ONLY the listed diagnostics. Keep everything else (exports, props, markup, styling) as is.
- Never silence a problem: no `any`, no `as unknown as`, no `@ts-ignore`, `@ts-expect-error` \
or `eslint-disable`.
- Do not add dependencies and do not touch package.json, tsconfig or lint configuration.
- Answer with the complete fixed file and nothing else: no explanation, no markdown fences.
- If the fix needs a file that does not exist yet, append it after the main file like this:
=== FILE: relative/path.tsx ===
<complete content of that file>
"""

_VISUAL_SYSTEM_PROMPT = """\
Autofix a generated React/TypeScript UI file so that the rendered page matches the reference \
design.

You get the reference design, a screenshot of the current page and a difference image in which \
mismatching areas are tinted red.

Rules:
- Change only markup and styling in this file: layout, spacing, sizes, colors, fonts and visible \
text. Keep exports, props, hooks and behaviour as they are.
- Never use `any`, `as unknown as`, `@ts-ignore`, `@ts-expect-error` or `eslint-disable`.
- Do not add dependencies and do not touch package.json, tsconfig or lint configuration.
- Answer with the complete changed file and nothing else: no explanation, no markdown fences.
- If styling belongs in a stylesheet that does not exist yet, append it after the main file like \
this:
=== FILE: relative/path.css ===
<complete content of that file>
"""


# ─────────────────────────────────────────────
# Pure helpers (R-01 … R-08)
# ─────────────────────────────────────────────

_NAMED_IMPORT = re.compile(
    r"^(?P<head>\s*import\s+(?:type\s+)?)(?P<clause>[^;{}]*?)(?:\{(?P<named>[^{}]*)\})?"
    r"\s*from\s*(?P<tail>['\"][^'\"]+['\"].*)$"
)


def r01_remove_unused_import(content: str, symbol: str) -> str:
    """R-01 (FT-LINT-001): drop ``symbol`` from a single-line import; keep the other names.

    Multi-line imports are returned unchanged (left to the model).
    """
    out: list[str] = []
    for line in content.splitlines(keepends=True):
        rewritten = _remove_from_import_line(line, symbol)
        if rewritten is not None:
            out.append(rewritten)
    return "".join(out)


def _remove_from_import_line(line: str, symbol: str) -> str | None:
    """Return the rewritten line, ``None`` to delete it, or ``line`` when it is not touched."""
    body = line.rstrip("\r\n")
    ending = line[len(body) :]
    match = _NAMED_IMPORT.match(body)
    if match is None:
        return line

    default = match["clause"].strip().rstrip(",").strip()
    named = [n.strip() for n in (match["named"] or "").split(",") if n.strip()]
    local_names = [n.split(" as ")[-1].strip() for n in named]
    if symbol not in {default, *local_names}:
        return line

    kept_default = "" if default == symbol else default
    kept_named = [n for n, local in zip(named, local_names, strict=True) if local != symbol]
    if not kept_default and not kept_named:
        return None

    parts = [kept_default] if kept_default else []
    if kept_named:
        parts.append("{ " + ", ".join(kept_named) + " }")
    return f"{match['head']}{', '.join(parts)} from {match['tail']}{ending}"


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
# Planner
# ─────────────────────────────────────────────


class AutoFixPlanner:
    """Deterministic import fixes first, then model repair per file. VALID-04."""

    def __init__(
        self,
        llm: LLMAdapter,
        model: str = DEFAULT_LIGHT_MODEL,
        *,
        repo_root: Path | None = None,
    ) -> None:
        self.llm = llm
        self._model = model
        self._repo_root = repo_root

    async def plan_and_apply(
        self,
        failures: list[FailureRecord],
        artifacts: Any,
        case_id: str,
        attempt_number: int,
        visual: VisualRegressionReport | None = None,
    ) -> tuple[FixAttempt, Any]:
        """Repair as many of ``failures`` as possible; report only what actually changed.

        Visual failures (the page does not match the design) are handled after all code
        diagnostics are gone, using the comparison images in ``visual``.
        """
        start = time.monotonic()
        all_ids = [f.id for f in failures]

        def finish(
            rule_id: str,
            description: str,
            patched: list[str],
            targeted: list[str],
        ) -> FixAttempt:
            return FixAttempt(
                attempt_number=attempt_number,
                case_id=case_id,
                trigger_failures=targeted,
                rule_id=rule_id,
                files_patched=patched,
                patch_description=description,
                success=bool(patched),
                remaining_failures=[i for i in all_ids if i not in targeted],
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if not failures:
            return finish("none", "No failures to fix", [], []), artifacts
        if not isinstance(artifacts, GeneratedArtifactSet) or not artifacts.files:
            return finish("none", "No generated file to patch", [], []), artifacts

        original = {f.path: f.content for f in artifacts.files}
        working = dict(original)
        new_files: dict[str, str] = {}
        rules: list[str] = []
        notes: list[str] = []
        addressed: list[str] = []

        # 1. Deterministic fixes.
        for failure in failures:
            path = failure.file_path
            if path not in working:
                continue
            fixed = _deterministic_fix(failure, path, working)
            if fixed is None:
                continue
            rule_id, new_content, note = fixed
            working[path] = new_content
            _remember(rules, rule_id)
            notes.append(note)
            addressed.append(failure.id)

        # 2. Model repair for the rest, one call per file.
        pending = [f for f in failures if f.id not in addressed]
        visual_failures = [f for f in pending if f.source == "visual"]
        pending = [f for f in pending if f.source != "visual"]
        by_file: dict[str, list[FailureRecord]] = {}
        for failure in pending:
            if failure.file_path in working:
                by_file.setdefault(str(failure.file_path), []).append(failure)
        consumers = [f for f in pending if f.file_path not in working]
        if not by_file and consumers:
            by_file = {path: [] for path in list(working)[:_MAX_CONSUMER_TARGETS]}

        for path, group in list(by_file.items())[:_MAX_FILES_PER_ATTEMPT]:
            outcome = await self._repair_file(path, group, consumers, working)
            addressed.extend(f.id for f in group)
            notes.append(outcome.note)
            if outcome.applied:
                _remember(rules, "R-09")
                working[path] = outcome.content
                new_files.update(outcome.new_files)

        # 3. Visual repair, only once no code diagnostics are left to fix.
        if visual_failures and not pending:
            addressed.extend(
                await self._repair_visual(visual_failures, visual, working, new_files, rules, notes)
            )

        patched = [p for p in working if working[p] != original[p]] + list(new_files)
        if not patched:
            reason = "; ".join(notes) or "nothing to change"
            return finish("none", f"No patch applied: {reason}", [], addressed), artifacts

        updated = _with_changes(artifacts, working, new_files)
        description = "; ".join(notes)
        return finish("+".join(rules), description, patched, addressed), updated

    async def _repair_visual(
        self,
        failures: list[FailureRecord],
        visual: VisualRegressionReport | None,
        working: dict[str, str],
        new_files: dict[str, str],
        rules: list[str],
        notes: list[str],
    ) -> list[str]:
        """Adjust the most likely UI files toward the design; return the failure ids handled."""
        if visual is None:
            notes.append("visual mismatch: no comparison images available")
            return []
        targets = _visual_targets(working)
        if not targets:
            notes.append("visual mismatch: no stylesheet or component file to adjust")
            return []
        images = _visual_images(visual)
        for path in targets:
            outcome = await self._repair_file(
                path, failures, [], working, visual=visual, images=images
            )
            notes.append(outcome.note)
            if outcome.applied:
                _remember(rules, "R-10")
                working[path] = outcome.content
                new_files.update(outcome.new_files)
        return [f.id for f in failures]

    async def _repair_file(
        self,
        path: str,
        group: list[FailureRecord],
        consumers: list[FailureRecord],
        working: dict[str, str],
        *,
        visual: VisualRegressionReport | None = None,
        images: list[tuple[str, str]] | None = None,
    ) -> _Repair:
        old = working[path]
        if visual is not None:
            system, prompt, purpose = (
                _VISUAL_SYSTEM_PROMPT,
                _visual_prompt(path, visual, working),
                "autofix-visual",
            )
        else:
            system = _AUTOFIX_SYSTEM_PROMPT
            prompt = _repair_prompt(path, group, consumers, working)
            purpose = "autofix"
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=prompt, images=images or None),
        ]
        config = LLMCallConfig(
            model=self._model,
            max_tokens=_REPAIR_MAX_TOKENS,
            temperature=0.0,
            metadata={"purpose": purpose},
        )
        response = await self.llm.complete(messages, config)

        if response.truncated:
            return _Repair(note=f"{path}: rejected model answer (truncated response)")
        try:
            main, extras = _parse_answer(response.content)
        except UnsafeRepositoryPathError:
            return _Repair(note=f"{path}: rejected model answer (extra file paths collide)")
        problem = _vet(old, main)
        if problem == "unchanged":
            return _Repair(note=f"{path}: model returned the file unchanged")
        if problem is not None:
            return _Repair(note=f"{path}: rejected model answer ({problem})")

        new_files: dict[str, str] = {}
        for extra_path, extra_content in extras.items():
            accepted = self._accept_extra(extra_path, extra_content, working)
            if accepted is not None:
                new_files[accepted] = extra_content
        extra_note = f" (+{len(new_files)} new file(s))" if new_files else ""
        counted = f"{len(group)} diagnostic(s)" if group else "related errors"
        note = (
            f"R-10: model adjusted {path} toward the design{extra_note}"
            if visual is not None
            else f"R-09: model repaired {path} ({counted}){extra_note}"
        )
        return _Repair(
            note=note,
            content=main,
            new_files=new_files,
            applied=True,
        )

    def _accept_extra(self, raw_path: str, content: str, working: dict[str, str]) -> str | None:
        """Return the normalised path of an extra file the model may add, else ``None``."""
        try:
            path = normalize_change_path(raw_path)
            ensure_distinct_paths([*working, path])
        except UnsafeRepositoryPathError:
            return None
        if not content.strip():
            return None
        if path in working or self._repo_root is None:
            return None
        try:
            target = resolve_change_path(self._repo_root, path)
        except UnsafeRepositoryPathError:
            return None
        return None if target.exists() else path


@dataclass
class _Repair:
    """Outcome of repairing one file."""

    note: str
    content: str = ""
    new_files: dict[str, str] = field(default_factory=lambda: dict[str, str]())
    applied: bool = False


def _remember(rules: list[str], rule_id: str) -> None:
    if rule_id not in rules:
        rules.append(rule_id)


# ─────────────────────────────────────────────
# Deterministic fixes
# ─────────────────────────────────────────────

_UNUSED_SYMBOL = re.compile(r"'(?P<symbol>[A-Za-z_$][\w$]*)'")
_MISSING_MODULE = re.compile(r"Cannot find module '(?P<spec>\.{1,2}/[^']+)'")


def _deterministic_fix(
    failure: FailureRecord, path: str, working: dict[str, str]
) -> tuple[str, str, str] | None:
    """Return ``(rule_id, new_content, note)`` when a safe rule applies and changes the file."""
    content = working[path]
    if failure.taxonomy_id == "FT-LINT-001":
        symbol = _UNUSED_SYMBOL.search(failure.message)
        if symbol is None:
            return None
        new = r01_remove_unused_import(content, symbol["symbol"])
        if new != content:
            return "R-01", new, f"R-01: removed unused import '{symbol['symbol']}' in {path}"
    if failure.taxonomy_id == "FT-BUILD-001":
        missing = _MISSING_MODULE.search(failure.message)
        if missing is None:
            return None
        target = _single_match(path, missing["spec"], working)
        if target is None:
            return None
        new = _rewrite_specifier(content, missing["spec"], target)
        if new != content:
            return "R-06", new, f"R-06: import '{missing['spec']}' -> '{target}' in {path}"
    return None


def _single_match(importer: str, spec: str, working: dict[str, str]) -> str | None:
    """Relative specifier of the one generated file whose name matches ``spec``, else ``None``."""
    wanted = Path(spec).name.lower()
    candidates = [
        p
        for p in working
        if p != importer
        and (
            Path(p).stem.lower() == wanted
            or (Path(p).stem.lower() == "index" and Path(p).parent.name.lower() == wanted)
        )
    ]
    if len(candidates) != 1:
        return None
    return _relative_specifier(importer, candidates[0])


def _relative_specifier(importer: str, target: str) -> str:
    target_path = Path(target)
    stem = target_path.parent if target_path.stem == "index" else target_path.with_suffix("")
    text = posixpath.relpath(stem.as_posix(), Path(importer).parent.as_posix() or ".")
    return text if text.startswith(".") else f"./{text}"


def _rewrite_specifier(content: str, old: str, new: str) -> str:
    escaped = re.escape(old)
    return re.sub(rf"(['\"]){escaped}\1", lambda m: f"{m[1]}{new}{m[1]}", content)


# ─────────────────────────────────────────────
# Model repair helpers
# ─────────────────────────────────────────────


def _repair_prompt(
    path: str,
    group: list[FailureRecord],
    consumers: list[FailureRecord],
    working: dict[str, str],
) -> str:
    lines = [f"File: {path}", ""]
    if group:
        lines.append("Diagnostics for this file:")
        lines.extend(f"- {_describe(f)}" for f in group)
    else:
        lines.append(
            "This file has no diagnostics of its own. The project reports errors elsewhere "
            "(below); change this file only if it is the cause, otherwise return it unchanged."
        )
    if consumers:
        lines += ["", "Errors in other files (you cannot edit those; adjust this file if needed):"]
        lines.extend(
            f"- {f.file_path or 'project'}: {_describe(f)}" for f in consumers[:_MAX_CONTEXT_ERRORS]
        )
    others = sorted(p for p in working if p != path)
    if others:
        lines += ["", "Other generated files: " + ", ".join(others)]
    lines += ["", "Current content (line numbers are for reference; do not output them):"]
    lines.extend(f"{n:>4} | {text}" for n, text in enumerate(working[path].splitlines(), start=1))
    return "\n".join(lines)


def _visual_targets(working: dict[str, str]) -> list[str]:
    """Stylesheets first, then the entry component: the files most likely to change the look."""

    def rank(path: str) -> tuple[int, int, str]:
        location = Path(path)
        entry = 0 if location.stem.lower() in _ENTRY_STEMS else 1
        return _UI_SUFFIXES.index(location.suffix.lower()), entry, path

    ui_files = [p for p in working if Path(p).suffix.lower() in _UI_SUFFIXES]
    return sorted(ui_files, key=rank)[:_MAX_VISUAL_TARGETS]


def _visual_images(visual: VisualRegressionReport) -> list[tuple[str, str]]:
    """Reference, current rendering and difference image, each shrunk to a size the model reads."""
    encoded = (
        encode_for_model(path)
        for path in (visual.reference_path, visual.generated_path, visual.diff_image_path)
    )
    return [image for image in encoded if image is not None]


def _visual_prompt(path: str, visual: VisualRegressionReport, working: dict[str, str]) -> str:
    lines = [
        f"File: {path}",
        "",
        "The rendered page does not match the reference design.",
        f"- SSIM {visual.ssim_score:.2f} (min {visual.threshold:.2f}); "
        f"{visual.mismatch_area_ratio:.1%} of the page differs "
        f"(max {visual.max_mismatch_ratio:.1%})"
        + (f"; viewport {visual.viewport}" if visual.viewport else ""),
    ]
    if visual.mismatch_regions:
        lines += ["", "Mismatching regions (x, y, width x height in design pixels):"]
        lines.extend(
            f"- x={r.x} y={r.y} {r.width}x{r.height} ({r.severity})"
            for r in visual.mismatch_regions[:_MAX_CONTEXT_ERRORS]
        )
    lines += [
        "",
        "Images, in this order: 1) reference design 2) current rendering "
        "3) difference (red = mismatch).",
    ]
    others = sorted(p for p in working if p != path)
    if others:
        lines += ["", "Other generated files: " + ", ".join(others)]
    lines += ["", "Current content (line numbers are for reference; do not output them):"]
    lines.extend(f"{n:>4} | {text}" for n, text in enumerate(working[path].splitlines(), start=1))
    return "\n".join(lines)


def _describe(failure: FailureRecord) -> str:
    where = f"line {failure.line_number}" if failure.line_number else "location unknown"
    label = failure.code or failure.taxonomy_id
    return f"{where} {label}: {failure.message}"


def _parse_answer(text: str) -> tuple[str, dict[str, str]]:
    """Split the model answer into the main file and any ``=== FILE: path ===`` extras."""
    headers = list(FILE_HEADER.finditer(text))
    ensure_distinct_paths([header["path"] for header in headers])
    main = text[: headers[0].start()] if headers else text
    extras: dict[str, str] = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        extras[header["path"]] = strip_fence(text[header.end() : end].lstrip("\n"))
    return strip_fence(main), extras


def _vet(old: str, new: str) -> str | None:
    """Return why ``new`` must not replace ``old`` (``"unchanged"`` for a no-op), else ``None``."""
    if not new.strip():
        return "empty answer"
    if new == old:
        return "unchanged"
    if len(old) >= _MIN_LENGTH_FOR_RATIO_CHECK and len(new) < _MIN_KEPT_RATIO * len(old):
        return "much shorter than the original, probably truncated"
    for marker in _SILENCERS:
        if new.count(marker) > old.count(marker):
            return f"adds {marker}"
    if len(_ANY_ESCAPE.findall(new)) > len(_ANY_ESCAPE.findall(old)):
        return "adds an `any` escape"
    return None


def _with_changes(
    artifacts: GeneratedArtifactSet,
    working: dict[str, str],
    new_files: dict[str, str],
) -> GeneratedArtifactSet:
    files = [
        f.model_copy(update={"content": working[f.path]}) if working[f.path] != f.content else f
        for f in artifacts.files
    ]
    files.extend(
        GeneratedFile(
            path=path,
            content=content,
            language=language_of(path),
            source_node_id="autofix",
            is_new=True,
        )
        for path, content in new_files.items()
    )
    return artifacts.model_copy(
        update={
            "files": files,
            "file_map": {f.path: f.content for f in files},
            "changed_paths": list(dict.fromkeys([*artifacts.changed_paths, *new_files])),
        }
    )
