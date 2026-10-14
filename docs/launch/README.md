# 공개 준비서

이 문서는 딸깍을 공개하기 전에 점검할 것, 채널별 게시 초안, 게시 뒤 운영 원칙을 모은 것입니다. **실제로
게시하는 일은 이 문서 어디에서도 하지 않았습니다.** 초안은 직접 읽고 고쳐서 직접 올리세요.

## 1. 기대치부터

스타 1만 개는 코드 품질만으로 얻을 수 없습니다. 노출이 먼저이고, 노출된 사람이 1분 안에 "되네"를 경험해야
스타로 이어집니다. 그래서 이 저장소는 코드보다 **첫 1분**에 힘을 실었습니다: API 키 없이 한 줄로 전체
절차를 보여 주는 `ddk demo`, 판정의 근거를 한 장으로 보여 주는 증거 보고서, 한계를 먼저 밝히는 README.

아래 숫자는 공개된 사례에서 본 대략의 경험칙이며 보장이 아닙니다.

| 일어날 수 있는 일 | 대략의 규모 | 조건 |
| --- | --- | --- |
| Hacker News Show HN 이 첫 화면에 오름 | 수백~수천 스타 | 시간대, 제목, 처음 30분의 반응에 크게 좌우됨 |
| GitHub Trending 진입 | 그 뒤 며칠간 꾸준한 유입 | 하루 스타 증가량이 비슷한 저장소보다 높아야 함 |
| 아무 일도 일어나지 않음 | 수십 스타 | 가장 흔한 결과이며, 실패가 아니라 다음 시도의 출발점 |

1만 개에 닿으려면 한 번의 게시가 아니라 몇 달에 걸친 반복이 필요합니다: 쓸 만한 사례를 쌓고, 의견을
반영해 고치고, 같은 이야기를 다른 모습으로 다시 올리는 일입니다. 아래 점검표는 그 반복의 첫 바퀴를 위한
것입니다.

## 2. 공개 전 점검표

코드가 아니라 **사람이 직접 해야 하는 일**입니다. 위에서부터 중요한 순서입니다.

- [ ] **실제 API 키로 `ddk run` 을 내 디자인 3개 이상에 실행해 보세요.** 지금까지 자동 검증은 대본 응답과
      녹화한 응답으로만 했습니다. 실제 모델이 내놓는 결과의 품질은 확인하지 못했습니다. 잘 나온 사례의 보고서와
      before/after 그림을 README 에 한두 개 넣고, 잘 안 나온 사례는 "한계"에 정직하게 적으세요.
- [ ] **저장소를 푸시한 뒤, 깨끗한 환경에서 첫 줄을 실행해 보세요.**
      `uvx --from git+https://github.com/dogskip/ddal-ggak ddk demo` 가 푸시 전에는 동작하지 않습니다. 모르는
      사람의 컴퓨터를 흉내 내려면 새 macOS 사용자 계정이나 Linux 컨테이너가 좋습니다. 지금까지 확인한 환경은
      macOS(arm64)뿐이며, Windows 는 확인하지 못했습니다.
- [ ] **GitHub 저장소 설정**: About 한 줄 설명, topics(`design-to-code`, `screenshot-to-code`,
      `claude`, `cli`, `playwright`, `visual-regression`, `llm`), 소셜 미리보기 이미지
      (`docs/assets/social-preview.png`, Settings → General → Social preview), Issues 켜기, Discussions 켜기.
- [ ] **PyPI 공개**: `.github/workflows/release.yml` 머리말의 세 단계를 따르세요. 2026-10-14 기준
      `ddalggak` 이름은 PyPI 에서 비어 있었습니다(조회 결과 404). 공개하면 설치 명령이 `pipx install ddalggak`
      으로 짧아집니다. 공개 전에 README 의 설치 명령도 함께 바꾸세요.
- [ ] **라이선스 확인**: `LICENSE` 의 저작권자를 `bjchoi` 로 가정해 두었습니다. 맞는 이름으로 고치세요.
- [ ] **추적 중인 로그 파일 정리**: `git rm --cached logs/mcp-logger-20260328-200900.log
      logs/mcp-logger-20260329-212901.log logs/stdio-server.log` (`.gitignore` 에는 이미 `logs/` 가 있습니다).
- [ ] **30초 영상 또는 GIF** 하나. README 의 터미널 그림(`docs/assets/demo.svg`)은 정지 화면이라, 움직이는
      것이 있으면 소셜 게시물의 반응이 달라집니다. `ddk demo` 를 화면 녹화로 찍으면 됩니다.
- [ ] **게시 뒤 24~48시간은 즉시 답할 수 있게** 시간을 비워 두세요. 첫 이슈에 빨리 답하는 저장소가 신뢰를
      얻습니다.

## 3. 한 줄 설명

같은 내용을 청중에 맞게 고르세요.

- 개발자 일반: *Design image in. Checked code out.*
- 기술 설명: *Generates code from a design image, then builds it, renders it in a real browser, compares it with the design and repairs what differs.*
- 신뢰 강조: *A model can write code; it can't mark its own homework. ddalggak decides from evidence on disk.*
- 한국어: **디자인 이미지를 넣으면, 빌드하고 브라우저로 비교해서 고친 코드가 나옵니다.**

피해야 할 표현: "pixel-perfect", "100% 정확", "개발자를 대체". 이 검사는 유사도 지표이고(README 의
"한계" 참고) 한계를 먼저 밝히면 오히려 신뢰를 얻습니다.

## 4. 게시 순서

1. **먼저 조용히**: 점검표를 끝내고, 친구 한두 명에게 첫 줄만 실행해 보게 하세요. 막히는 곳을 고칩니다.
2. **Show HN**: 평일 미국 동부 오전이 흔히 권장됩니다(한국 시간으로는 밤입니다). 시간대 효과는 경험칙입니다.
3. **같은 날 또는 다음 날**: Reddit, X, 한국 채널. 한꺼번에 올리면 답글을 놓칩니다. 채널당 하루씩이 낫습니다.
4. **그다음 주**: dev.to 또는 Hashnode 글, Product Hunt, 해당하는 awesome 목록에 PR.
5. **매주**: 의견을 반영한 변경 기록(CHANGELOG)을 근거로 "이번 주에 고친 것" 짧은 글.

**하지 말아야 할 것**: 스타를 부탁하거나 교환하기, 지인을 동원한 대량 추천(Hacker News 는 이를 감지해 순위를
내립니다), 봇이나 구매, 다른 도구를 깎아내리는 비교표, 같은 글을 여러 게시판에 복사해 붙이기.

## 5. 채널별 초안

각 채널의 자기 홍보 규칙은 자주 바뀌므로 **올리기 전에 해당 게시판의 규칙을 직접 읽으세요.** 아래 초안은
시작점입니다.

### 5.1 Hacker News — Show HN

제목 (80자 이하, 과장 없이):

```
Show HN: ddalggak – design image to code, checked in a real browser
```

본문 (첫 댓글로 올립니다):

```
Hi HN. ddalggak (ddk) generates code from a design image for your own repo, then checks its own work
instead of handing it over: it builds the project, type-checks and lints it, serves it, opens it in
headless Chromium at the size of your design, compares the screenshot with the design (block SSIM plus
the share of the page that differs strongly), and sends the miss back to the model with the design, the
screenshot and a red difference image. What comes out is a verdict (ready / manual review / blocked)
and one HTML report that shows the evidence. Nothing touches your repo until `ddk apply`.

You can see the whole loop without an API key:

    uvx --from git+https://github.com/dogskip/ddal-ggak ddk demo

It replays a recorded model reply; npm ci, build, tsc, eslint, Chromium and the comparison are real. The
first draft misses the design (SSIM 0.89), the loop catches it, the second attempt passes.

What it can't do, so you don't have to find out: the check is grayscale block SSIM (a colour change with
the same brightness can pass), it compares only the first image at that image's size, remote fonts and
images are blocked in the browser, and previews work for Vite, Next.js and Astro only. The real-model
path has had much less use than the demo, so expect rough edges.

I'd like to hear where the report is unclear, which design it gets wrong, and what check you'd want in
the verdict. Repo: https://github.com/dogskip/ddal-ggak
```

### 5.2 Reddit

게시판마다 자기 홍보 비율과 말머리 규칙이 다릅니다(r/webdev, r/reactjs, r/ClaudeAI, r/SideProject,
r/opensource 등). 먼저 규칙을 읽고, 해당 게시판에 맞는 말머리를 고르세요. 본문은 HN 초안을 줄여서 사용합니다.
제목 예:

```
I built a CLI that generates code from a design image and then checks it in a real browser (no API key needed for the demo)
```

before/after 그림(`docs/assets/before-after.png`)을 첨부하면 글이 더 잘 읽힙니다.

### 5.3 Product Hunt

- 이름: ddalggak
- 한 줄: `Design image in. Checked code out.`
- 설명: `ddalggak turns a design image into code for your repo, then proves it: build, type-check, lint, a real-browser screenshot compared with your design, automatic repair, and a verdict with evidence. Try the demo without an API key.`
- 첫 댓글: HN 본문과 같은 내용을 짧게. 한계를 먼저 적습니다.
- 갤러리: `before-after.png`, `report.png`, `demo.svg` 대신 영상.

Product Hunt 는 개발자 도구에서 효과가 제한적입니다. 우선순위는 낮습니다.

### 5.4 dev.to / Hashnode 글 개요

제목: *Why I made a code generator mark its own homework with a headless browser*

1. 문제: 이미지에서 코드를 만드는 일은 쉽고, 맞는지 아는 일이 어렵다.
2. 해법: 검사를 모델 밖으로 꺼낸다 (빌드, 타입, 린트, 스크린샷 비교).
3. 데모 그림: 첫 시안 SSIM 0.89, 차이 이미지, 수정 뒤 1.00.
4. 숫자가 속이는 곳: 회색조 SSIM 의 맹점, 단조로운 화면, 동적 요소 (README "한계").
5. 판정을 모델에게 맡기지 않은 이유: 증거 묶음과 판정 규칙.
6. 직접 해보기: 데모 한 줄.

### 5.5 Lobsters, Indie Hackers, AlternativeTo

- Lobsters 는 초대제이므로 계정이 있을 때만 올립니다. 제목은 중립적으로, 태그는 `ai`, `show` 등을 확인하세요.
- Indie Hackers 는 "무엇을 만들었고 무엇을 배웠나" 형식이 맞습니다.
- AlternativeTo 는 비슷한 도구의 대안으로 등록하는 곳입니다. 등록하려면 비교 대상을 정해야 합니다.

### 5.6 한국 채널 (OKKY, 커리어리, velog, 클리앙, GeekNews, oss.kr)

한국어 초안 (OKKY·커리어리·클리앙용, 길이는 게시판에 맞춰 줄이세요):

```
디자인 이미지에서 코드를 생성하고, 그 결과를 스스로 검증하는 CLI 를 만들었습니다. (오픈소스, MIT)

- 프로젝트를 빌드하고 타입 검사와 린트를 실행합니다.
- 결과 화면을 실제 헤드리스 Chromium 으로 열어 디자인 이미지와 비교합니다 (SSIM + 크게 다른 면적 비율).
- 어긋나면 디자인, 스크린샷, 빨간색 차이 이미지를 모델에게 돌려주어 고치게 합니다.
- 마지막에 ready / manual-review / blocked 판정과, 근거를 보여 주는 HTML 보고서 한 장을 냅니다.
- `ddk apply` 를 실행하기 전에는 내 저장소에 아무것도 기록하지 않습니다.

API 키 없이 전체 절차를 볼 수 있는 데모가 있습니다.

    uvx --from git+https://github.com/dogskip/ddal-ggak ddk demo

한계도 README 에 적어 두었습니다. 회색조 SSIM 이라 밝기가 같은 색 변화는 통과할 수 있고, 미리보기는 Vite,
Next.js, Astro 만 지원합니다. 실제 모델로 돌려 본 경험은 아직 데모보다 적습니다. 어색한 곳이나 결과가
나빴던 디자인을 알려 주시면 큰 도움이 됩니다. 저장소: https://github.com/dogskip/ddal-ggak
```

- velog 는 5.4 의 개요를 한국어로 풀어 쓴 글이 어울립니다. 제목 예: *코드 생성기의 결과를 모델이 아니라 헤드리스 브라우저로 평가하게 했다*.
- GeekNews(news.hada.io)는 이 목록에 제가 더한 후보입니다. 자기 프로젝트 소개 글은 `Show GN:` 말머리를
  붙이는 것으로 알고 있으니, 올리기 전에 규칙을 확인하세요.
- oss.kr 은 한국 오픈소스 정보를 모으는 곳이므로 등록 가능 여부와 방법을 직접 확인하세요.

### 5.7 awesome 목록과 MCP 목록

- "screenshot-to-code", "design-to-code", "Claude Code" 관련 awesome 목록에 한 줄 PR 을 보냅니다. 저장소마다
  기여 규칙(정렬 순서, 설명 길이)이 있으니 가장 최근에 병합된 PR 을 따라 하세요.
- **MCP 목록은 지금 올리지 않는 것을 권합니다.** 현재 MCP 서버는 Design Studio(`design_new`, `preflight`,
  `ddk_version`)만 제공하고, 이미지에서 코드까지의 절차는 노출하지 않습니다. 지금 올리면 사용자가 기대하는 것과
  실제가 어긋납니다. 이미지에서 코드까지를 MCP 도구로 노출한 뒤에 올리세요 (6장 참고).

## 6. 스타 가능성을 실제로 키우는 일 (우선순위)

1. **실제 모델 결과 사례 모으기** (점검표 1번). 이것이 없으면 데모는 "녹화된 것"으로만 보입니다.
2. **MCP 로 이미지에서 코드까지 노출.** 에이전트 도구(Claude Code, Cursor)를 사용하는 사람이 이 저장소의 가장
   큰 잠재 사용자입니다. 현재는 CLI 만 됩니다.
3. **미리보기 서버 확대**: SvelteKit, Nuxt, Remix, 일반 Webpack 설정. 지금은 Vite, Next.js, Astro 외에는
   `--no-visual` 이 필요해서 첫인상에서 걸릴 수 있습니다.
4. **여러 이미지·여러 화면 크기 비교** (반응형 확인).
5. **영상**과 짧은 사례 글.

## 7. 게시 뒤 운영

- 댓글에는 방어하지 말고 먼저 재현하세요. "보고서를 첨부해 주실 수 있나요?"가 좋은 첫 답입니다. 보고서는 한 파일이라
  첨부하기 쉽습니다.
- 버그 이슈 서식에는 `ddk version`, `ddk doctor` 출력, 보고서 파일을 요청하세요.
- 일주일 단위로 GitHub 의 Insights → Traffic 에서 유입 경로(Referring sites)를 확인하고, 반응이 있던 채널에 집중하세요.
- 스타 수보다 **첫 실행 성공률**을 보세요: 이슈에 "설치가 안 된다"가 많으면 점검표 2번으로 돌아갑니다.
