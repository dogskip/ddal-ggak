"""Unit tests for IntakeProcessor (INGEST-02)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ddk.models.input import CaseInput
from ddk.services.intake_processor import IntakeProcessor


@pytest.fixture
def processor() -> IntakeProcessor:
    return IntakeProcessor()


@pytest.fixture
def valid_case_input(tmp_path: Path) -> CaseInput:
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지",
        repo_path=tmp_path,
    )


class TestIntakeProcessor:
    async def test_process_valid_input(
        self, processor: IntakeProcessor, valid_case_input: CaseInput
    ) -> None:
        result, hashes = await processor.process(valid_case_input)
        assert result.case_id == "C-001"
        assert len(hashes) == 1

    async def test_image_hash_computed(
        self, processor: IntakeProcessor, valid_case_input: CaseInput
    ) -> None:
        _, hashes = await processor.process(valid_case_input)
        img_path = valid_case_input.image_paths[0]
        expected = hashlib.sha256(img_path.read_bytes()).hexdigest()[:16]
        assert hashes[str(img_path)] == expected
        assert len(expected) == 16

    async def test_image_not_found(self, processor: IntakeProcessor, tmp_path: Path) -> None:
        case_input = CaseInput(
            case_id="C-002",
            image_paths=[tmp_path / "nonexistent.png"],
            prompt="테스트",
            repo_path=tmp_path,
        )
        with pytest.raises(FileNotFoundError, match="nonexistent.png"):
            await processor.process(case_input)

    async def test_multiple_images(self, processor: IntakeProcessor, tmp_path: Path) -> None:
        imgs = []
        for i in range(3):
            p = tmp_path / f"img{i}.png"
            p.write_bytes(f"image-{i}".encode())
            imgs.append(p)
        case_input = CaseInput(
            case_id="C-003",
            image_paths=imgs,
            prompt="멀티 이미지",
            repo_path=tmp_path,
        )
        _, hashes = await processor.process(case_input)
        assert len(hashes) == 3
        for p in imgs:
            assert str(p) in hashes
            assert len(hashes[str(p)]) == 16

    async def test_returns_original_case_input(
        self, processor: IntakeProcessor, valid_case_input: CaseInput
    ) -> None:
        result, _ = await processor.process(valid_case_input)
        assert result is valid_case_input


class TestIntakeNode:
    async def test_intake_node_thin_adapter(self, tmp_path: Path) -> None:
        from ddk.graph.nodes.intake import intake_node

        img = tmp_path / "design.png"
        img.write_bytes(b"\x89PNG")
        case_input = CaseInput(
            case_id="C-001",
            image_paths=[img],
            prompt="테스트",
            repo_path=tmp_path,
        )
        state = {"case_input": case_input}
        result = await intake_node(state)
        assert result["current_node"] == "intake"
        assert result["case_input"].case_id == "C-001"
