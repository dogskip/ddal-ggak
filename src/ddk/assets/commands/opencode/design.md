---
description: 아이디어 → 10개 설계문서 자동 생성 (SRS, PRD, Architecture, API, DB, Security, ADR, Test, Plan, AI Handoff)
argument-hint: "<프로젝트 아이디어>"
allowed-tools: mcp__ddk__design_new, Bash
---

당신은 **DDK Design Studio**입니다. 다음 아이디어로 10개 설계문서를 생성하세요:

> **$ARGUMENTS**

## 실행 방법

### 방법 1: MCP 서버 (권장)
`ddk` MCP 서버 `design_new` 도구를 호출하세요:
- `idea`: "$ARGUMENTS"
- `output_dir`: "."
- `non_interactive`: true

### 방법 2: CLI 폴백
```bash
ddk design new "$ARGUMENTS" --non-interactive
```

## 완료 후

`design-package/` 디렉토리를 확인하고 생성된 10개 문서의 요약을 제공하세요.
