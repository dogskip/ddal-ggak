# User guide

How to run ddalggak on your own project, read what it reports, and deal with what it gets wrong.
The [README](../README.md) has the overview and the settings table; this guide has the details.
Korean: [USER-GUIDE.ko.md](USER-GUIDE.ko.md).

## 1. Install

You need Python 3.12+, [uv](https://docs.astral.sh/uv/) (or pipx or pip), Node.js 20.19+ or 22.12+
with npm, and a Chrome, Edge or Chromium. The Node.js version that matters is the one your own project
needs; the demo's Vite 7 needs the versions above.

```bash
uv tool install git+https://github.com/dogskip/ddal-ggak    # puts `ddk` on your PATH
ddk --help
```

Without installing: `uvx --from git+https://github.com/dogskip/ddal-ggak ddk <command>`.

## 2. Check the machine

```bash
ddk doctor
```

Each line is a check: Python, uv, API key, Node.js, git, headless Chromium. A failing required check
exits with 1; warnings are optional parts. If the browser line warns, run
`ddk doctor --install-browser` (downloads Playwright's headless Chromium, about 100 MB, once) or install
Chrome. A browser is found in this order: `DDK_CHROMIUM_PATH`, Playwright's Chromium, an installed
Chrome, Chromium or Edge. On a bare Linux image, Chromium also needs system libraries; Playwright's
`install-deps chromium` installs them.

## 3. Try the demo

```bash
ddk demo                  # or: ddk demo --workdir ./demo-out to keep the files
```

The demo copies a small Vite + React + TypeScript project to a temporary folder, installs it with
`npm ci`, and runs the whole loop on a built-in wireframe. A recorded model reply stands in for the
API, so no key is needed. The first draft is deliberately a little off; the loop catches it with the
screenshot comparison, repairs it, and ends `ready`. The last lines name the files to open, the
evidence report first.

## 4. Run it on your design

### Prepare the repository

- It has a `package.json`, and its dependencies are installed (`npm install`, or the equivalent for
  pnpm, yarn or bun). Otherwise pass `--install`: the dependencies then install in the temporary copy,
  with lifecycle scripts off.
- It has something to check: a `build` script, a TypeScript setup, an ESLint setup. A project with none
  of them has nothing to verify, and the verdict is `blocked`.
- For the screenshot comparison it uses Vite, Next.js or Astro, because the built app must be served
  to be seen. Anything else needs `--no-visual`.
- Commit or stash your own work first. `ddk run` leaves your files alone (see section 7 for what it adds),
  but `ddk apply` writes into them.

### Run

```bash
export ANTHROPIC_API_KEY=sk-ant-...
ddk run design.png
ddk run hero.png pricing.png -p "Next.js app router, Tailwind, keep the existing Button"
```

The image can be PNG, JPEG, WebP or GIF; it is scaled to at most 1568 px on the long edge before it is
sent to the model. With several images, all of them are shown to the model when it writes code and
infers the design system, while the design analysis and the screenshot comparison use the **first**
image. Without `-p` the model is asked to implement the image as it is, following your repository's
conventions.

Progress prints one line per stage: intake, repository scan, design analysis, design-system inference,
plan, generation, convention cleanup, validation (build, types, lint, screen with its SSIM), each
auto-fix attempt, and the verdict. Before any model call, a missing key, an unreadable image or a
browser that cannot start stops the run (exit 1), so a doomed run costs nothing.

The run ends with a panel (case id, verdict, score, report path) and an exit code: **0** for `ready`,
**1** for any other verdict or a run that could not start, **2** for invalid settings. `--json` prints
the same as JSON on stdout (progress goes to stderr), which is what scripts and agents should read:
`release_decision`, `terminal_state`, `scorecard_overall` and `report`, the path of the report.

### Read the result

```bash
ddk report --open      # one HTML page: verdict, both comparison rounds, fixes, checks, scores
ddk status             # case state, verdict, number of fix attempts (latest case; --case-id C-002)
ddk certify            # verdict with the scorecard and the evidence pack
```

In the report, start with the verdict card, then the screenshot rounds: *Design*, *Result*, and the
*Difference* in red. Drag the bar on the overlay to flip between the result and the design. The
*Checks* table lists build, typecheck, lint and visual with the time each took; skipped steps give
their reason. The *Scorecard* is four sub-scores (precision, maintainability, automation,
scalability) averaged. Fixed formulas compute them from the check results, the repair history and
the convention cleanup; no model is asked for a grade.

| Verdict | Meaning | What to do |
| --- | --- | --- |
| `ready` | No blocking finding, score 0.85 or higher | Read the report, then `ddk apply` |
| `manual-review` | Auto-fix gave up, or the score is below 0.85 | Open the report; apply by hand, or adjust the prompt and run again |
| `blocked` | A check failed, the page could not be compared, nothing could be verified, or the environment could not run the checks | The report lists the blockers; fix the cause and run again |

### Apply

```bash
ddk apply --dry-run    # a table: create / update / unchanged / conflict / rejected, per file
ddk apply              # write the files
```

`ddk apply` refuses cases that are not `ready`. It writes only where the repository still holds the
version the run started from, or no file yet. Any conflict or unsafe path stops all writes. Replaced
files are copied to `.ddk/cases/<id>/artifacts/replaced/`. Review both versions before resolving a
conflict; `--force` and `--allow-blocked` are compatibility options that now exit with code 2.

`ddk rollback` also exits with code 2: whole-repository resets are disabled. For an existing-change
case, use the separate [verified-change workflow](VERIFIED-CHANGES.md): `change export` provides a
review package, `change apply` records its owned transaction, and `change recover` handles an
interrupted transaction after checking current file contents. It does not undo legacy image-run
applies or completed transactions. Preserve your own Git changes and review the backups when
reconciling a legacy apply.

## 5. Steering a run

| You want | Do |
| --- | --- |
| A different instruction | `-p "..."` |
| A stricter or looser match | `--ssim-threshold 0.95`, `--max-mismatch 0.01` (or the `DDK_*` variables) |
| More or fewer repair rounds | `DDK_MAX_RETRY_ATTEMPTS` (1 to 10, default 3) |
| A cheaper run | `DDK_LLM_MODEL` / `DDK_LIGHT_MODEL`, and `DDK_COST_CAP_USD` as the ceiling |
| To skip the screenshot comparison | `--no-visual` (the report records it as waived) |
| Another case id or repository | `--case-id C-007`, `--repo ../other-app` |

Cost: every model call is recorded with its tokens and price in the case folder
(`llm-calls.json`, and the totals in the report). `DDK_COST_CAP_USD` (default 2.0) stops new calls
once it is reached; the call in flight can overshoot.

## 6. What is checked

`ddk` reads only your project's own files and never guesses a command:

- **build**: the `build` script of `package.json`.
- **typecheck**: a `typecheck`, `type-check`, `check-types` or `tsc` script; otherwise `tsc --noEmit`
  when there is a `tsconfig.json` and TypeScript is a dependency (solution-style `references` are
  followed).
- **lint**: a `lint` script; otherwise ESLint when there is an ESLint configuration and ESLint is a
  dependency.
- **visual**: the project's own `vite preview`, `next start` or `astro preview` on loopback, opened in
  headless Chromium at the size of the first design image, as a full-page screenshot.

The package manager follows the lockfile (pnpm, yarn, bun, else npm). A step the project does not
have is *skipped* with its reason; if every step is skipped, nothing was verified and the verdict is
`blocked`. Console errors and failed requests seen while the page loads count as failures.

The browser may only reach loopback addresses. Remote fonts, images and APIs are blocked, so a page
that needs them renders without them, and the comparison sees that.

## 7. The evidence on disk

```
.ddk/                           the only folder `ddk run` adds; it ignores itself, so git skips it
  cases/C-001/
    artifacts/
      generated/                the files the model wrote (what `ddk apply` copies)
      inputs/                   your design image(s)
      visual/round-1/…          screenshot, difference image and numbers of each comparison
      replaced/                 files an `ddk apply` replaced
    reports/
      report.html               the evidence report
      release-decision.json     the verdict and its blockers
      scorecard.json            the four sub-scores and the grade
      evidence-pack.json        timings, cost, the terminal state
      fix-attempts.json         each repair: rule, files, outcome
      runtime-validation-report.json   every check with its command, exit code and time
      llm-calls.json            every model call with tokens, cost and model
      …                         plan, design analysis, repository profile, status
```

`ddk report` rebuilds the HTML from these files only, and `report.html` is one self-contained file
(pictures included, nothing fetched from the web), so it can be sent to a colleague as it is.

Besides `.ddk/`, a run creates one git ref per repair round, `refs/ddk/fix/<case>/attempt-N`, pointing
at the commit that was checked out. These are historical checkpoints, not permission to reset the
repository; `ddk rollback` is disabled. A repository without history gets none.

## 8. When it goes wrong

| What you see | Why, and what to do |
| --- | --- |
| `No Anthropic API key found` | Set `ANTHROPIC_API_KEY` or `DDK_ANTHROPIC_API_KEY`, or put it in `.env` |
| `No Chromium found; run: ddk doctor --install-browser…` | Run that, install Chrome, or set `DDK_CHROMIUM_PATH`. `--no-visual` skips the comparison |
| `dependencies are not installed; run \`<install command>\` or pass --install` | Install in your repository first, or pass `--install` |
| `no preview command for this project (supported: vite, next, astro)` | The page cannot be served for comparison; use `--no-visual` |
| `vite is declared but not installed in node_modules` | Install dependencies |
| `No build, type-check or lint step applied…, so nothing was verified` | Add a build script, a `tsconfig.json` or an ESLint configuration |
| The visual check keeps failing on a page that looks right | Open the report. Animation, random or live data, remote fonts or a different viewport differ between runs; fix the design file or loosen `--max-mismatch` |
| `manual-review` after the repair rounds | The same failure came back or the budget ran out. The report shows the last diagnostics; apply what is good by hand |
| Cost cap reached | Raise `DDK_COST_CAP_USD`, or use a cheaper `DDK_LLM_MODEL` |
| Output in the wrong language | `DDK_LANG=en` or `DDK_LANG=ko` |

If something else looks wrong, `DDK_LOG_LEVEL=DEBUG ddk run …` prints the details.

## 9. Design Studio

A separate part of the tool: it turns an idea into ten design documents (SRS, PRD, architecture,
API, database, security, decisions, tests, plan and a hand-off for AI assistants).

```bash
ddk design new "an AI code review tool"          # asks a few questions first
ddk design new "an AI code review tool" -y -o ./docs   # no interview, custom folder
```

It needs the API key too. See [DESIGN-STUDIO.md](DESIGN-STUDIO.md) for the details.

## 10. Agents and MCP

```bash
ddk install --detect       # which AI coding tools were found
ddk install --claude       # or --cursor, --codex, --gemini, --opencode, --copilot, --kiro, --all
```

This adds `/ddk:design` (or the tool's equivalent) and registers `ddk serve` with five tools:
`design_new`, `preflight`, `ddk_version`, `ddk_verify` and `ddk_status`. Existing-change verification
requires prepared fixed inputs and isolated execution; MCP does not expose apply, recovery or
trusted-local execution. See the [verified-change guide](VERIFIED-CHANGES.md).

Image-to-code remains CLI-only. An agent with a shell tool can run `ddk run <image> --json` and read
`release_decision` and `report`. Planned capabilities and completion criteria are in the
[roadmap](../ROADMAP.md).
