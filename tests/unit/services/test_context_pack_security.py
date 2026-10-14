"""Security tests for ContextPackBuilder — no secrets reach the LLM context.

These guard the #1 commercial risk: the tool shipping a customer's credentials
to a third-party model. Both defense layers are exercised: secret *files* are
never read, and inline secrets in included files are redacted.
"""

from __future__ import annotations

from pathlib import Path

from ddk.services.context_pack_builder import ContextPackBuilder

# A syntactically valid (fake) Anthropic key that redact_string must catch.
_FAKE_KEY = "sk-ant-" + "a" * 40


def _seed_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text('{"name": "app"}', encoding="utf-8")
    (root / "src" / "App.tsx").write_text(
        f'const client = createClient("{_FAKE_KEY}");\nexport default App;\n',
        encoding="utf-8",
    )
    # Secrets that must NOT leave the machine.
    (root / ".env").write_text(f"ANTHROPIC_API_KEY={_FAKE_KEY}\n", encoding="utf-8")
    (root / "server.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nMIIabc\n-----END PRIVATE KEY-----\n", encoding="utf-8"
    )
    (root / ".env.example").write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")


def test_secret_files_excluded_from_context(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    pack = ContextPackBuilder().build(target_files=["src/App.tsx"], repo_path=tmp_path)
    paths = {chunk.path for chunk in pack.chunks}
    assert ".env" not in paths
    assert "server.pem" not in paths


def test_inline_secret_redacted_in_included_file(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    pack = ContextPackBuilder().build(target_files=["src/App.tsx"], repo_path=tmp_path)
    app_chunk = next(c for c in pack.chunks if c.path == "src/App.tsx")
    assert _FAKE_KEY not in app_chunk.content
    assert "[REDACTED]" in app_chunk.content


def test_raw_secret_absent_from_entire_pack(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    pack = ContextPackBuilder().build(target_files=["src/App.tsx"], repo_path=tmp_path)
    blob = "\n".join(chunk.content for chunk in pack.chunks)
    assert _FAKE_KEY not in blob


def test_env_templates_are_excluded_from_automatic_context(tmp_path: Path) -> None:
    _seed_repo(tmp_path)
    pack = ContextPackBuilder().build(target_files=["src/App.tsx"], repo_path=tmp_path)
    assert not {".env", ".env.example"}.intersection(c.path for c in pack.chunks)


def test_symlinked_file_outside_repository_is_never_read(tmp_path: Path) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external.ts"
    external.write_text("EXTERNAL_SECRET_MARKER", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "package.json").write_text('{"name":"app"}', encoding="utf-8")
    (tmp_path / "src" / "linked.ts").symlink_to(external)

    pack = ContextPackBuilder().build(target_files=["src/New.ts"], repo_path=tmp_path)

    assert "src/linked.ts" not in {chunk.path for chunk in pack.chunks}
    assert "EXTERNAL_SECRET_MARKER" not in "\n".join(chunk.content for chunk in pack.chunks)
