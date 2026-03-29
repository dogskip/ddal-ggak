"""ddalggak MCP 서버 — FastMCP 기반 Design Studio 엔진."""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ddk")  # description 파라미터 미지원 버전 호환


@mcp.tool()
async def design_new(
    idea: str,
    output_dir: str = ".",
    non_interactive: bool = True,
) -> str:
    """아이디어에서 10개 설계문서 생성.

    (SRS, PRD, Architecture, API, DB, Security, ADR, Test, Plan, AI Handoff)

    Args:
        idea: 프로젝트 아이디어 또는 설명 (자유 텍스트)
        output_dir: design-package/ 를 저장할 디렉토리 (기본값: 현재 디렉토리)
        non_interactive: True이면 인터뷰 없이 즉시 생성 (MCP 환경 기본값)

    Returns:
        생성된 문서 목록, 비용, 경로를 담은 JSON 문자열
    """
    from .adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415
    from .design import DesignGenerator, DesignInterviewer, DesignWriter  # noqa: PLC0415
    from .design.interviewer import InterviewResult  # noqa: PLC0415
    from .models.config import DdalggakConfig  # noqa: PLC0415

    cfg = DdalggakConfig()

    if not cfg.anthropic_api_key:
        return json.dumps(
            {
                "success": False,
                "error": "ANTHROPIC_API_KEY 미설정. 방법: export DDK_ANTHROPIC_API_KEY=sk-ant-...",
            }
        )

    llm = ClaudeAdapter(
        api_key=cfg.anthropic_api_key,
        default_model=cfg.llm_model,
        cost_cap_usd=cfg.cost_cap_usd,
    )
    out_path = Path(output_dir)

    # MCP 환경에서는 인터랙티브 인터뷰 불가 → non_interactive 기본값 True
    if non_interactive:
        interview_result: InterviewResult = InterviewResult(
            project_name=idea[:50],
            original_idea=idea,
        )
    else:
        interviewer = DesignInterviewer(llm=llm, model=cfg.llm_model)

        def ask_fn(question: str) -> str:  # pragma: no cover
            return input(f"\n{question}\n> ")

        interview_result = await interviewer.run(idea=idea, ask_fn=ask_fn)

    generator = DesignGenerator(llm=llm, model=cfg.llm_model, concurrency=3)
    gen_result = await generator.generate_all(interview_result)

    writer = DesignWriter(output_dir=out_path)
    pkg_dir = writer.write(gen_result, interview_result)

    return json.dumps(
        {
            "success": True,
            "project": interview_result.project_name,
            "documents_generated": len(gen_result.documents),
            "errors": len(gen_result.errors),
            "cost_usd": round(gen_result.total_cost_usd, 4),
            "output_dir": str(pkg_dir),
            "documents": [d.key for d in gen_result.documents],
        },
        ensure_ascii=False,
    )


@mcp.tool()
def preflight() -> str:
    """DDK 환경 점검 — API 키, Python 버전, 의존성 확인.

    Returns:
        각 항목 점검 결과를 담은 JSON 문자열
    """
    import sys  # noqa: PLC0415

    from .models.config import DdalggakConfig  # noqa: PLC0415

    results: list[dict[str, object]] = []

    py_ok = sys.version_info >= (3, 12)
    results.append({"check": "Python >= 3.12", "ok": py_ok, "detail": sys.version.split()[0]})

    try:
        cfg = DdalggakConfig()
    except Exception:  # noqa: BLE001
        cfg = DdalggakConfig.model_construct()
    api_ok = bool(cfg.anthropic_api_key)
    detail = "설정됨" if api_ok else "없음"
    results.append({"check": "DDK_ANTHROPIC_API_KEY", "ok": api_ok, "detail": detail})

    try:
        import anthropic as _  # noqa: F401, PLC0415

        results.append({"check": "anthropic SDK", "ok": True, "detail": "installed"})
    except ImportError:
        results.append(
            {
                "check": "anthropic SDK",
                "ok": False,
                "detail": "설치 필요: uv add anthropic",
            }
        )

    all_ok = all(bool(r["ok"]) for r in results)
    return json.dumps({"all_ok": all_ok, "checks": results}, ensure_ascii=False)


@mcp.tool()
def ddk_version() -> str:
    """현재 설치된 DDK 버전 반환.

    Returns:
        버전 문자열 (예: "0.1.0")
    """
    try:
        from importlib.metadata import version  # noqa: PLC0415

        return version("ddalggak")
    except Exception:  # noqa: BLE001
        return "0.0.0-dev"


def run_server() -> None:
    """MCP 서버 진입점 — stdio transport로 실행."""
    mcp.run()
