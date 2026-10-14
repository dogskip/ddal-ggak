"""Design Studio generator — 인터뷰 결과로 10개 설계문서를 생성한다."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from ..adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ..models.config import DEFAULT_PRIMARY_MODEL
from .interviewer import InterviewResult
from .templates import TEMPLATES


@dataclass
class GeneratedDocument:
    """단일 생성 문서."""

    key: str  # e.g. "01-srs"
    filename: str  # e.g. "01-srs.md"
    content: str
    cost_usd: float = 0.0


@dataclass
class GenerationResult:
    """10개 문서 생성 결과."""

    documents: list[GeneratedDocument] = field(default_factory=lambda: [])
    total_cost_usd: float = 0.0
    errors: dict[str, str] = field(default_factory=lambda: {})


class DesignGenerator:
    """LLM으로 10개 설계 문서를 생성한다."""

    def __init__(
        self,
        llm: LLMAdapter,
        model: str = DEFAULT_PRIMARY_MODEL,
        concurrency: int = 3,
    ) -> None:
        self._llm = llm
        self._model = model
        self._concurrency = concurrency

    async def generate_all(
        self,
        interview: InterviewResult,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> GenerationResult:
        """10개 문서를 비동기로 생성한다.

        Args:
            interview: 인터뷰 결과 (요구사항, 대화 내역)
            on_progress: 진행 상황 콜백 (doc_key, current, total)

        Returns:
            GenerationResult — 생성된 문서 목록과 총 비용
        """
        result = GenerationResult()
        total = len(TEMPLATES)
        semaphore = asyncio.Semaphore(self._concurrency)

        async def generate_one(idx: int, key: str) -> None:
            async with semaphore:
                if on_progress:
                    on_progress(key, idx, total)
                try:
                    doc = await self._generate_document(key, interview)
                    result.documents.append(doc)
                    result.total_cost_usd += doc.cost_usd
                except Exception as exc:  # noqa: BLE001
                    result.errors[key] = str(exc)

        tasks = [generate_one(idx, key) for idx, key in enumerate(TEMPLATES.keys(), 1)]
        await asyncio.gather(*tasks)

        # Sort documents in template order
        order = list(TEMPLATES.keys())
        result.documents.sort(key=lambda d: order.index(d.key) if d.key in order else 999)
        return result

    async def _generate_document(self, key: str, interview: InterviewResult) -> GeneratedDocument:
        template = TEMPLATES[key]
        user_msg = template.user.format(
            project_name=interview.project_name,
            original_idea=interview.original_idea,
            interview_summary=interview.summary,
            interview_transcript=interview.transcript,
        )
        messages = [
            Message(role="system", content=template.system),
            Message(role="user", content=user_msg),
        ]
        resp = await self._llm.complete(
            messages,
            LLMCallConfig(model=self._model, temperature=0.0, max_tokens=8192),
        )
        ext = ".yaml" if key == "04-api-spec" else ".md"
        return GeneratedDocument(
            key=key,
            filename=f"{key}{ext}",
            content=resp.content,
            cost_usd=resp.cost_usd,
        )
