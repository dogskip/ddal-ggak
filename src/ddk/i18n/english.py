"""English text for each Korean message passed to ``t``."""

from __future__ import annotations

ENGLISH: dict[str, str] = {
    "❌ 강제 반영은 제공하지 않습니다. 내보내기 후 충돌을 해결하세요.": (
        "❌ Forced application is disabled. Export the changes and resolve the conflict."
    ),
    "❌ Git 전체 초기화 복구는 제공하지 않습니다. 관리된 반영 기록으로 복구하세요.": (
        "❌ Whole-repository reset is disabled. Recover using an owned application record."
    ),
    "이전 복구 명령의 중단 사유와 안전한 대안을 표시합니다.": (
        "Explain why legacy rollback is disabled and show the safe alternative."
    ),
    "   변경을 내보낸 뒤 현재 파일과 충돌을 해결하세요.": (
        "   Export the changes and resolve conflicts with the current files."
    ),
    "   `ddk status`로 원인을 확인한 후 변경을 내보내세요.": (
        "   Check the cause with `ddk status`, then export the changes."
    ),
    "호환 옵션: 사용하면 내보내기 안내와 함께 중단합니다": (
        "Compatibility option: stop with export guidance"
    ),
    "파일 변경 없이 반영 계획을 표시합니다": ("Show the application plan without changing files"),
    # --- application and global options
    "딸깍 — 디자인 이미지에서 코드를 생성하고, 실제 브라우저로 화면을 비교하고, "
    "자동 수정과 증거 기반 판정을 거칩니다.": (
        "ddalggak — generates code from a design image, compares the rendered page with the "
        "design in a real browser, auto-fixes it, and certifies the result with evidence."
    ),
    "Design Studio — 아이디어에서 설계 문서를 생성합니다": (
        "Design Studio — turn an idea into design documents"
    ),
    "로그 수준": "Log level",
    "출력 폴더 (design new 에서 사용)": "Output folder (used by design new)",
    # --- settings and shared errors
    "❌ 설정 오류 — 환경 변수나 .env 값을 확인하세요:": (
        "❌ Invalid settings — check your environment variables or .env:"
    ),
    " (입력값: {value})": " (got: {value})",
    "❌ ANTHROPIC API 키가 없습니다.": "❌ No Anthropic API key found.",
    "   설정 방법: export DDK_ANTHROPIC_API_KEY=sk-ant-...": (
        "   Set it with: export DDK_ANTHROPIC_API_KEY=sk-ant-..."
    ),
    "            또는 export ANTHROPIC_API_KEY=sk-ant-...": (
        "   or:          export ANTHROPIC_API_KEY=sk-ant-..."
    ),
    "   또는 .env 파일에 DDK_ANTHROPIC_API_KEY=... 추가": (
        "   or add DDK_ANTHROPIC_API_KEY=... to a .env file"
    ),
    "❌ 조회할 case가 없습니다. 먼저 `ddk run`을 실행하세요.": (
        "❌ No cases found. Run `ddk run` first."
    ),
    "❌ case 폴더를 찾을 수 없습니다: {path}": "❌ Case folder not found: {path}",
    "❌ 아직 지원하지 않는 LLM provider: {name}": "❌ LLM provider not supported yet: {name}",
    "❌ 아직 지원하지 않는 sandbox mode: {name}": "❌ Sandbox mode not supported yet: {name}",
    # --- run
    "디자인 이미지와 프롬프트로 전체 절차를 실행합니다.": (
        "Run the whole loop on a design image: generate, build, compare in a browser, "
        "auto-fix, certify."
    ),
    "입력 디자인 이미지 경로 (1개 이상)": "Design image paths (one or more)",
    "생성 지시 프롬프트 (생략하면 이미지를 그대로 구현)": (
        "Instruction for the model (default: implement the image as it is)"
    ),
    "대상 저장소 폴더": "Target repository folder",
    "명시적 case ID": "Case ID to use",
    "JSON으로 출력": "Print JSON",
    "일시 사본에 의존성 설치 (--ignore-scripts); 원본 의존성은 복사하지 않습니다": (
        "Install dependencies in the disposable copy (--ignore-scripts); "
        "source dependencies are not copied"
    ),
    "렌더링 화면과 디자인 이미지 비교 (기본: 켜짐). --no-visual 은 비교를 면제합니다.": (
        "Compare the rendered page with the design image (default: on). "
        "--no-visual waives the comparison."
    ),
    "화면 유사도(SSIM) 통과 기준 (기본 0.92)": (
        "Minimum screenshot similarity (SSIM) to pass (default 0.92)"
    ),
    "디자인과 크게 다른 면적 비율의 허용 한도 (기본 0.03)": (
        "Largest share of the page that may differ strongly from the design (default 0.03)"
    ),
    "❌ 입력 이미지를 찾을 수 없습니다: {paths}": "❌ Design image not found: {paths}",
    "❌ 이미지로 읽을 수 없는 파일입니다: {paths}": "❌ Not a readable image: {paths}",
    "❌ 화면 비교에 사용할 브라우저를 시작할 수 없습니다: {error}": (
        "❌ The browser for the screenshot comparison cannot start: {error}"
    ),
    "   비교를 건너뛰려면 --no-visual 을 붙이세요 (건너뛴 사실은 보고서에 남습니다).": (
        "   To skip the comparison, add --no-visual (the report records that it was skipped)."
    ),
    # --- status, certify
    "저장된 case 상태를 조회합니다.": "Show the saved state of a case.",
    "저장된 판정 결과를 조회합니다.": "Show the saved verdict of a case.",
    "조회할 case ID": "Case ID to show (default: latest)",
    # --- apply
    "검증을 통과한 case의 생성 파일을 저장소에 적용합니다.": (
        "Write the generated files of a verified case into the repository."
    ),
    "적용할 case ID (기본: 가장 최근)": "Case ID to apply (default: latest)",
    "❌ case 결과를 읽을 수 없습니다: {error}": "❌ Cannot read the case result: {error}",
    "❌ 판정이 ready가 아니라서 적용하지 않습니다 (현재: {decision}).": (
        "❌ Not applied: the verdict is not ready (now: {decision})."
    ),
    "[green]✅ {count}개 파일을 적용했습니다[/green]": "[green]✅ Applied {count} file(s)[/green]",
    "❌ 쓸 수 없는 경로가 있어 아무것도 적용하지 않았습니다.": (
        "❌ Nothing applied: some paths cannot be written."
    ),
    "❌ 실행 뒤에 바뀐 파일이 있어 아무것도 적용하지 않았습니다.": (
        "❌ Nothing applied: some files changed after the run."
    ),
    "새 파일": "new",
    "수정": "modified",
    "변경 없음": "unchanged",
    "충돌": "conflict",
    "거부": "rejected",
    "ddk apply (계획)": "ddk apply (plan)",
    "파일": "File",
    "작업": "Action",
    "비고": "Note",
    # --- rollback
    "복구할 fix attempt 번호": "Fix attempt to restore",
    "복구할 case ID": "Case ID to restore",
    # --- demo
    "API 키 없이 전체 절차를 체험합니다: 디자인 → 코드 → 화면 비교 → 자동 수정 → 판정.": (
        "Try the whole loop without an API key: design → code → screenshot comparison → "
        "auto-fix → verdict."
    ),
    "결과를 보관할 새 폴더 (기본: 임시 폴더)": (
        "New folder to keep the result (default: a temporary folder)"
    ),
    "ddk demo — 모델 응답은 미리 녹화한 것을 재생하고, 빌드·브라우저·화면 비교는 "
    "실제로 실행합니다 (API 키 불필요).": (
        "ddk demo — the model replies are recorded; the build, the browser and the screenshot "
        "comparison are real (no API key needed)."
    ),
    "작업 폴더: {path}": "Work folder: {path}",
    "프로젝트 복사와 의존성 설치(npm ci)로 시작합니다…": (
        "Starting with the project copy and the dependency install (npm ci)…"
    ),
    "첫 시도: SSIM {ssim:.2f}, 디자인과 크게 다른 면적 {mismatch:.1%} → 화면 비교에서 걸림": (
        "First attempt: SSIM {ssim:.2f}, {mismatch:.1%} of the page differs strongly from the "
        "design → caught by the screenshot comparison"
    ),
    "자동 수정 {attempts}회 뒤: SSIM {ssim:.2f}": (
        "After {attempts} auto-fix attempt(s): SSIM {ssim:.2f}"
    ),
    "판정: {decision}": "Verdict: {decision}",
    "디자인(와이어프레임)": "Design (wireframe)",
    "첫 시도 화면": "First-attempt screenshot",
    "차이 표시(빨강)": "Difference (red)",
    "수정 뒤 화면": "Screenshot after the fix",
    "생성된 코드": "Generated code",
    "파일 (작업 폴더 기준):": "Files (relative to the work folder):",
    "\n내 디자인으로: ddk run <이미지> (ANTHROPIC_API_KEY 필요)": (
        "\nWith your own design: ddk run <image> (needs ANTHROPIC_API_KEY)"
    ),
    "Node.js 와 npm 이 필요합니다 (https://nodejs.org).": (
        "Node.js and npm are required (https://nodejs.org)."
    ),
    "헤드리스 Chromium 을 사용할 수 없습니다: {detail}": (
        "Headless Chromium is not available: {detail}"
    ),
    "헤드리스 Chromium 이 없습니다. 지금 내려받을까요? (한 번만, 디스크 약 200MB)": (
        "No headless Chromium found. Download it now? (one time, about 200 MB on disk)"
    ),
    "Chromium 을 내려받는 중입니다…": "Downloading Chromium…",
    # --- proof, audit
    "기능 대응표를 실제 증거 파일로 검증하고, 주장해도 되는 항목만 출력합니다. "
    "증거가 디스크에 있고 관문 조건을 채울 때만 allowed 로 표시됩니다.": (
        "Check the capability matrix against the evidence files on disk and print only the "
        "claims you may make. A claim is allowed only when its evidence exists and the gate "
        "conditions are met."
    ),
    "superset claim이 허용되지 않으면 비정상 종료(코드 1)": (
        "Exit with code 1 when the superset claim is not allowed"
    ),
    "[red]❌ capability matrix 로드 실패:[/red] {error}": (
        "[red]❌ Could not load the capability matrix:[/red] {error}"
    ),
    "국제표준 조항 → 산출물 대응 범위를 검증합니다 (인증이 아니라 대응 범위 확인).": (
        "Check which clauses of the listed standards map to an artifact (a coverage check, "
        "not a certification)."
    ),
    "benchmarks/compliance-matrix.json 생성": "Write benchmarks/compliance-matrix.json",
    "gap이 있으면 비정상 종료(코드 1)": "Exit with code 1 when there is a gap",
    "[red]❌ 표준 목록 로드 실패:[/red] {error}": (
        "[red]❌ Could not load the standards catalog:[/red] {error}"
    ),
    "[green]✅ 대응표 작성:[/green] {path}": "[green]✅ Compliance matrix written:[/green] {path}",
    "\n[dim]coverage = clauses fully mapped / total · 인증이 아니라 조항 대응 범위입니다.[/dim]": (
        "\n[dim]coverage = clauses fully mapped / total · this is clause coverage, "
        "not a certification.[/dim]"
    ),
    # --- design new
    "아이디어 → 인터뷰 → 10개 설계 문서 자동 생성.": (
        "Idea → interview → ten design documents, generated."
    ),
    '예시: ddk design new "AI 기반 코드 리뷰 도구" -y': (
        'Example: ddk design new "an AI code review tool" -y'
    ),
    "프로젝트 아이디어 (자유 텍스트)": "Project idea (free text)",
    "인터뷰 없이 바로 생성": "Generate right away, without the interview",
    "출력 폴더": "Output folder",
    "\n[bold]Step 1/2:[/bold] 요구사항 인터뷰\n": (
        "\n[bold]Step 1/2:[/bold] Requirements interview\n"
    ),
    "\n[green]인터뷰 완료[/green] — {questions}개 질문, {requirements}개 요구사항 도출\n": (
        "\n[green]Interview done[/green] — {questions} question(s), "
        "{requirements} requirement(s) found\n"
    ),
    "[bold]Step 2/2:[/bold] 설계 문서 생성 (10개)\n": (
        "[bold]Step 2/2:[/bold] Writing the design documents (10)\n"
    ),
    "\n[bold green]✅ 완료![/bold green]": "\n[bold green]✅ Done![/bold green]",
    " ⚠️ {count}개 실패": " ⚠️ {count} failed",
    "   문서: {count}개 생성{warn}": "   Documents: {count} written{warn}",
    "   비용: ${cost:.4f} USD": "   Cost: ${cost:.4f} USD",
    "   위치: [cyan]{path}[/cyan]": "   Location: [cyan]{path}[/cyan]",
    "\n[yellow]실패한 문서:[/yellow] {names}": "\n[yellow]Failed documents:[/yellow] {names}",
    "  자세한 내용: design-package/ERRORS.md": "  Details: design-package/ERRORS.md",
    # --- preflight, doctor, init, serve, install
    "환경 점검 — API 키, Python 버전, 의존성 확인.": (
        "Environment check — API key, Python version, dependencies."
    ),
    "환경 점검 — Python, uv, API 키, Node.js, git, 헤드리스 Chromium 확인.": (
        "Environment check — Python, uv, API key, Node.js, git and headless Chromium."
    ),
    "먼저 헤드리스 Chromium 을 내려받습니다 (Playwright 사용, 한 번만)": (
        "Download the headless Chromium first (through Playwright, one time)"
    ),
    "❌ Chromium 을 내려받지 못했습니다. 네트워크를 확인하거나 Chrome 을 설치하세요.": (
        "❌ Chromium could not be downloaded. Check the network, or install Google Chrome."
    ),
    "설정 값": "Settings",
    ".ddk/ 작업 폴더를 초기화합니다 (이미 있으면 안전하게 건너뜀).": (
        "Create the .ddk/ work folder (an existing one is left alone)."
    ),
    "프로젝트 루트 경로": "Project root",
    "[green]✅ .ddk/ 초기화 완료:[/green] {path}": "[green]✅ .ddk/ ready:[/green] {path}",
    "MCP 서버를 stdio 방식으로 시작합니다 (Claude Code, Cursor 등이 호출).": (
        "Start the MCP server on stdio (called by Claude Code, Cursor and similar tools)."
    ),
    "AI 도구에 등록하려면: ddk install --all": (
        "To register it with your AI tools: ddk install --all"
    ),
    "AI 코딩 도구에 /ddk:design 명령과 MCP 서버를 등록합니다.": (
        "Register the /ddk:design command and the MCP server with AI coding tools."
    ),
    "예시: ddk install --detect · ddk install --claude · ddk install --all": (
        "Examples: ddk install --detect · ddk install --claude · ddk install --all"
    ),
    "Claude Code에 설치": "Install into Claude Code",
    "Gemini CLI에 설치": "Install into Gemini CLI",
    "OpenCode에 설치": "Install into OpenCode",
    "OpenAI Codex CLI에 설치": "Install into OpenAI Codex CLI",
    "GitHub Copilot에 설치": "Install into GitHub Copilot",
    "Cursor에 설치": "Install into Cursor",
    "Kiro에 설치": "Install into Kiro",
    "감지된 모든 도구에 설치": "Install into every detected tool",
    "프로젝트 로컬 설치 (기본) vs 홈 폴더 전역 설치": (
        "Install for this project (default) or globally in your home folder"
    ),
    "설치 없이 감지된 도구만 출력": "List the detected tools without installing",
    "[bold]감지된 AI 도구:[/bold]": "[bold]Detected AI tools:[/bold]",
    "[yellow]감지된 AI 도구 없음[/yellow]": "[yellow]No AI tools detected[/yellow]",
    "[yellow]설치할 도구를 지정하세요. 예: ddk install --all[/yellow]": (
        "[yellow]Say which tools to install into, for example: ddk install --all[/yellow]"
    ),
    "  감지 먼저: ddk install --detect": "  To see what is detected first: ddk install --detect",
    "[bold cyan]DDK 설치[/bold cyan] → {tools}\n": (
        "[bold cyan]Installing DDK[/bold cyan] → {tools}\n"
    ),
    "\n[green]{done}/{total}개 도구 설치 완료[/green]": (
        "\n[green]Installed into {done} of {total} tool(s)[/green]"
    ),
    "\n[bold]다음 단계:[/bold]": "\n[bold]Next:[/bold]",
    "  1. AI 도구를 재시작하세요": "  1. Restart your AI tool",
    '  2. /ddk:design "쇼핑몰" 명령을 실행하세요': '  2. Run /ddk:design "online store"',
    # --- evidence report
    "저장된 case의 증거 보고서(HTML 한 장)를 만듭니다.": (
        "Write the evidence report (one HTML page) of a saved case."
    ),
    "대상 case ID (기본: 가장 최근)": "Case ID to report on (default: latest)",
    "저장할 파일 (기본: case 폴더의 reports/report.html)": (
        "File to write (default: reports/report.html in the case folder)"
    ),
    "만든 뒤 기본 브라우저로 엽니다": "Open it in the default browser afterwards",
    "❌ 보고서를 쓸 수 없습니다: {error}": "❌ Cannot write the report: {error}",
    "✅ 보고서 작성: {path}": "✅ Report written: {path}",
    "증거 보고서": "Evidence report",
    "{path} 에 release-decision.json 이 없어 보고서를 만들 수 없습니다": (
        "No release-decision.json in {path}, so there is nothing to report"
    ),
    "딸깍 증거 보고서 · {case_id}": "ddalggak evidence report · {case_id}",
    "ddk {version} 이(가) 이 case 폴더의 파일만으로 만든 보고서입니다.": (
        "Report built by ddk {version} from the files in this case folder only."
    ),
    "적용 가능": "Ready to apply",
    "차단됨": "Blocked",
    "사람 검토 필요": "Needs human review",
    "점수": "Score",
    "등급": "grade",
    "소요 {seconds:.1f}초": "{seconds:.1f}s",
    "비용 ${cost:.4f}": "cost ${cost:.4f}",
    "모델 호출 {count}회": "{count} model call(s)",
    "자동 수정 {count}회": "{count} auto-fix attempt(s)",
    "화면 비교": "Visual comparison",
    "통과": "Passed",
    "미달": "Not met",
    "{number}회차 검증": "Check {number}",
    "SSIM {ssim:.2f} (기준 {threshold:.2f}) · 디자인과 크게 다른 면적 {share:.1%} "
    "(허용 {allowed:.1%})": (
        "SSIM {ssim:.2f} (threshold {threshold:.2f}) · {share:.1%} of the page differs "
        "strongly from the design (allowed {allowed:.1%})"
    ),
    "결과 화면": "Result",
    "차이 (빨강)": "Difference (red)",
    "디자인": "Design",
    "이미지를 불러올 수 없습니다": "Image not available",
    "디자인과 겹쳐 보기": "Overlay on the design",
    "겹침 위치": "Overlay position",
    "왼쪽은 결과 화면, 오른쪽은 디자인입니다. 막대를 끌어 비교하세요.": (
        "Result on the left, design on the right. Drag the bar to compare."
    ),
    "회차": "Attempt",
    "규칙": "Rule",
    "조치": "Action",
    "고친 파일": "Files changed",
    "결과": "Outcome",
    "검사 단계": "Checks",
    "실패": "Failed",
    "건너뜀": "Skipped",
    "실행 불가": "Could not run",
    "단계": "Step",
    "상태": "Status",
    "시간": "Time",
    "내용": "Detail",
    "점수표": "Scorecard",
    "정밀도": "Precision",
    "유지보수성": "Maintainability",
    "자동화": "Automation",
    "확장성": "Scalability",
    "문제": "Problems",
    "차단 항목": "Blockers",
    "실패 기록": "Failures",
    "생성된 파일": "Generated files",
    "{count}줄": "{count} lines",
    "실행 정보": "Run details",
    "지시": "Instruction",
    "판정 시각": "Decided at",
    "모델": "Models",
    "토큰 (입력 / 출력)": "Tokens (in / out)",
    "화면 크기": "Viewport",
    # --- progress lines
    "입력 확인": "Intake",
    "저장소 분석": "Repository scan",
    "디자인 분석": "Design analysis",
    "디자인 시스템 추론": "Design-system inference",
    "생성 계획": "Generation plan",
    "코드 생성": "Code generation",
    "관례 정리": "Convention cleanup",
    "검증": "Validation",
    "자동 수정": "Auto-fix",
    "판정": "Verdict",
    "빌드": "build",
    "타입": "types",
    "린트": "lint",
    "화면": "screen",
    " — 영역 {regions}개 · 컴포넌트 {components}개": (
        " — {regions} region(s) · {components} component(s)"
    ),
    " — 파일 {count}개": " — {count} file(s)",
    " — {count}개 수정": " — {count} modified",
    ", 건너뜀: {rules}": ", skipped: {rules}",
    " (SSIM {ssim:.2f}, 기준 {threshold:.2f})": (" (SSIM {ssim:.2f}, threshold {threshold:.2f})"),
    " {number}회차 — {note}": " attempt {number} — {note}",
    " (점수 {score:.2f})": " (score {score:.2f})",
    " — 사람 확인 필요: {reason}": " — needs a human: {reason}",
}
