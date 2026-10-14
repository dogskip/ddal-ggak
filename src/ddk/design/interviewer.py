"""Design Studio interviewer — LLM이 프로젝트 아이디어를 인터뷰한다."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

from ..adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ..models.config import DEFAULT_PRIMARY_MODEL

_SYSTEM = """당신은 세계 최고의 소프트웨어 요구사항 엔지니어입니다.
사용자의 막연한 아이디어를 구체적인 소프트웨어 요구사항으로 발전시키는 인터뷰를 진행합니다.

인터뷰 규칙:
- 한 번에 질문은 반드시 1개만 합니다 (복수 질문 금지)
- 사용자 답변을 바탕으로 다음 질문을 자연스럽게 이어가십시오
- 5~10개 질문 후 인터뷰를 종료하십시오
- 질문 영역: 타겟 사용자, 핵심 기능, 기술 스택 선호, 규모, 보안 요구사항, 성능 요구사항, 주요 차별점

응답 형식 (반드시 JSON):
{
  "question": "다음 질문 텍스트 (없으면 null)",
  "done": true/false,
  "extracted": ["이 턴에서 도출된 요구사항들"]
}
"""


@dataclass
class InterviewResult:
    """인터뷰 완료 후 결과물."""

    project_name: str
    original_idea: str
    turns: list[dict[str, str]] = field(default_factory=lambda: [])  # [{"q": ..., "a": ...}]
    extracted_requirements: list[str] = field(default_factory=lambda: [])

    @property
    def transcript(self) -> str:
        lines: list[str] = []
        for i, turn in enumerate(self.turns, 1):
            lines.append(f"Q{i}: {turn['q']}")
            lines.append(f"A{i}: {turn['a']}")
            lines.append("")
        return "\n".join(lines)

    @property
    def summary(self) -> str:
        parts = [f"원래 아이디어: {self.original_idea}", "", "인터뷰 대화:"]
        parts.append(self.transcript)
        parts.append("도출된 요구사항:")
        parts.extend(f"- {r}" for r in self.extracted_requirements)
        return "\n".join(parts)


class DesignInterviewer:
    """LLM 기반 Design Studio 인터뷰어."""

    def __init__(self, llm: LLMAdapter, model: str = DEFAULT_PRIMARY_MODEL) -> None:
        self._llm = llm
        self._model = model

    async def run(
        self,
        idea: str,
        ask_fn: Callable[[str], str],
        max_turns: int = 10,
    ) -> InterviewResult:
        """인터뷰를 실행하고 결과를 반환한다.

        Args:
            idea: 사용자 원래 아이디어 문자열
            ask_fn: 터미널/UI에 질문을 표시하고 답변을 받는 콜백 (sync)
            max_turns: 최대 인터뷰 턴 수

        Returns:
            InterviewResult — 인터뷰 전문과 추출된 요구사항
        """
        project_name = _extract_project_name(idea)
        conversation: list[Message] = [
            Message(role="system", content=_SYSTEM),
            Message(
                role="user",
                content=f"사용자의 프로젝트 아이디어: {idea!r}\n\n인터뷰를 시작하세요.",
            ),
        ]

        turns: list[dict[str, str]] = []
        all_requirements: list[str] = []

        for _ in range(max_turns):
            resp = await self._llm.complete(
                conversation,
                LLMCallConfig(model=self._model, temperature=0.0, max_tokens=1024, effort="low"),
            )
            parsed = _parse_interview_response(resp.content)
            extracted = parsed.get("extracted")
            if isinstance(extracted, list):
                for item in cast(list[object], extracted):
                    if isinstance(item, str):
                        all_requirements.append(item)
                    elif item is not None:
                        all_requirements.append(str(item))

            if parsed.get("done") or not parsed.get("question"):
                break

            question = str(parsed["question"])
            answer = ask_fn(question)  # Sync I/O — handled by CLI layer

            turns.append({"q": question, "a": answer})
            conversation.append(Message(role="assistant", content=resp.content))
            conversation.append(Message(role="user", content=answer))

        return InterviewResult(
            project_name=project_name,
            original_idea=idea,
            turns=turns,
            extracted_requirements=all_requirements,
        )


def _parse_interview_response(content: str) -> dict[str, object]:
    """LLM 응답에서 JSON 파싱 — 실패 시 graceful fallback."""
    stripped = content.strip()
    # LLM이 code block으로 감쌌을 때 처리
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        stripped = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped
    try:
        parsed: dict[str, object] = json.loads(stripped)
        return parsed
    except json.JSONDecodeError:
        # Fallback: 텍스트 전체를 question으로 취급
        return {"question": stripped, "done": False, "extracted": []}


def _extract_project_name(idea: str) -> str:
    """아이디어에서 간단한 프로젝트 이름을 추출한다."""
    # 30자 이하면 그대로, 길면 첫 30자 + "..." 프로젝트
    if len(idea) <= 30:
        return idea
    return idea[:30] + "..."
