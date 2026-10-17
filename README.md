# ddalggak

**Design image in. Checked code out.**

[![CI](https://github.com/dogskip/ddal-ggak/actions/workflows/ci.yml/badge.svg)](https://github.com/dogskip/ddal-ggak/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

English · [한국어](README.ko.md)

`ddk` turns a design image into code for your own repository, then checks its own work. It builds the
project, type-checks and lints it, renders the page in a real headless browser, compares the
screenshot with your design, repairs what differs, and only then says whether the result is safe to
apply. Generated source is applied only after an explicit apply command.

<picture>
  <source media="(max-width: 600px)" srcset="docs/assets/before-after-mobile.png">
  <img src="docs/assets/before-after.png" alt="Recorded schematic demo: reference design, first attempt and result after repair">
</picture>

This demo uses a schematic dashboard and recorded model replies. The three images show the
reference, the first attempt and the repaired result. The red difference overlay is in the report below.

## Try it in a minute, no API key

```bash
uvx --from git+https://github.com/dogskip/ddal-ggak ddk demo
```

You need [uv](https://docs.astral.sh/uv/), Node.js (20.19+ or 22.12+) with npm, and a Chrome, Edge or
Chromium. With none installed, `ddk demo` offers to download a headless Chromium (about 100 MB, once).

![Output of ddk demo](docs/assets/demo.svg)

The demo replays a recorded model reply, which is why it needs no key. Everything around it is real:
`npm ci`, build, type-check, lint, a preview server, headless Chromium and the screenshot comparison.
The first draft misses the design (SSIM 0.89), the loop catches that, applies a repair, and the second
attempt passes (SSIM 1.00).

## Verify changes already in your repository

`ddk up "Change heading and preserve navigation" --dry-run --json` shows the plan.
`ddk change init --discover --json` suggests an unapproved draft. Review its independent target and preservation
checks, then publish them with `ddk change init --approve-draft --json`. `ddk up ... --trusted-local` captures Git
changes, freezes the actual environment, checks them in headless Chromium and exports review evidence.
Add `--repair --confirm-provider` for bounded repair or `--apply` with the storage/quiescence
confirmations for managed application. Missing acceptance checks block before execution.

[One-command guide](docs/ONECLICK.md) covers `init`, `doctor`, `up`, `probe`, native test reports,
policy checks, rebuildable SQLite/FTS5, bounded evidence retrieval, current-source gates, offline replay
and the eleven verified-change MCP tools.
The image workflow below remains available with its separate legacy contract.

## Use it on your own design

```bash
uv tool install git+https://github.com/dogskip/ddal-ggak     # pipx and pip work too
export ANTHROPIC_API_KEY=sk-ant-...

cd my-vite-app                       # a repository with a package.json; run npm install first
ddk run design.png                   # add -p "dark theme, reuse our Button" to steer it
ddk report --open                    # the evidence report, one HTML page
ddk apply --dry-run                  # which files would change
ddk apply                            # write them; anything replaced is backed up first
```

Without `node_modules` the checks cannot run, so either install first or pass `--install` (installs in
the temporary copy with lifecycle scripts off). `ddk run` exits 0 when the verdict is `ready`, 1 for any
other verdict or a run that could not start, and 2 for invalid settings.

![The evidence report of the demo run](docs/assets/report.png)

## How it works

1. **Read.** Scans the repository (framework, conventions, styling) and analyses the design image with
   Claude's vision: regions, components, tokens.
2. **Generate.** Plans the files and writes them in the style of your code base.
3. **Check.** Copies the repository to a temporary folder and runs what the project defines: build,
   type-check, lint. A step the project does not have is reported as skipped, with the reason.
4. **Compare.** Serves the built app on loopback, opens it in headless Chromium at the size of your
   design, takes a screenshot and compares it with the design (SSIM plus the share of the page that
   differs strongly).
5. **Repair.** Failures are classified. Two deterministic fixes run first (unused imports, wrong
   relative imports). Then the model repairs one file at a time from its diagnostics, and only when no
   code diagnostic is left does it fix a visual miss, from the design, the screenshot and the red
   difference image. It is told not to add dependencies or touch `package.json`, `tsconfig` or the lint
   configuration, and its answer is thrown away if it is empty, truncated or silences the checker
   (`any`, `@ts-ignore`, `eslint-disable`). Rounds stop at `DDK_MAX_RETRY_ATTEMPTS` (default 3) or when
   the same failure returns.
6. **Decide.** The verdict comes from the evidence on disk, not from the model's own claim.

| Verdict | When |
| --- | --- |
| `ready` | no blocking finding and a score of 0.85 or higher |
| `manual-review` | auto-fix gave up (rounds used up, or the same failure came back), or the score is below 0.85 |
| `blocked` | a check failed, the page could not be compared, nothing could be verified, or the environment could not run the checks |

Every case keeps its files under `.ddk/cases/C-NNN/`: the verdict, scorecard, evidence pack, each fix
attempt, every model call with its cost, and a screenshot of every comparison round.

## The visual check, and what it cannot see

A comparison passes when **SSIM ≥ 0.92** and **at most 3 %** of the page differs strongly. Both limits
are settings (`--ssim-threshold`, `--max-mismatch`, or `DDK_SSIM_THRESHOLD`, `DDK_MAX_MISMATCH_RATIO`).
`--no-visual` waives the comparison; the report records that it was waived. Without a supported
preview server or a browser, an image-based run is blocked rather than passed on trust.

Know the limits before trusting a green result:

- SSIM here is computed on grayscale blocks, so a change of colour with the same brightness can pass.
- A near-blank or very flat design is easy to match; the check tells you little about it.
- Only the first design image is compared, at the size of that image.
- Anything that changes between loads (animation, random or live data) can fail a correct page.
- The browser may only reach loopback addresses, so remote fonts and images do not load.
- Similarity is a proxy, not a design review. Read the report before you apply.

## Safety

- Generated files go to a temporary copy of your repository; `ddk apply` is the only step that writes
  your files. A run adds a `.ddk/` folder (it ignores itself) and, in a git repository, a ref
  `refs/ddk/fix/<case>/attempt-N` per repair round; that is all. A file you edited since the run is
  reported as a conflict, and nothing is written until you resolve it.
- The copy leaves out `.git`, `.env`, key and credential files, which are also never read into a
  prompt. Build commands run with a short environment allow-list and a `HOME` inside the copy, so
  your API key and your home folder are not handed to them.
- Dependencies install with `--ignore-scripts`. The commands that may run are an allow-list
  (`npm`, `pnpm`, `yarn`, `bun`, `npx`, `node`, `tsc`, `vite`, `git`, `python`, `python3`, `pytest`).
- The temporary copy is not an operating-system sandbox: your project's own build scripts still run
  on your machine. Treat generated code like a stranger's pull request and review the diff.
- `DDK_COST_CAP_USD` (default 2.0) stops new model calls once that much is spent; the call in flight
  can finish past it.

## Commands

| Command | What it does |
| --- | --- |
| `ddk demo` | The whole loop on a built-in page, no API key |
| `ddk run <image>…` | Generate, check, compare, repair, decide |
| `ddk report` | Write the evidence report of a case (`--open` shows it) |
| `ddk apply` | Apply a legacy image-run `ready` case; `--dry-run` previews it; conflicts block writes |
| `ddk status`, `ddk certify` | The saved state and verdict of a case |
| `ddk init`, `ddk up`, `ddk probe` | Prepare a case, verify/repair existing Git changes, capture headless evidence; [guide](docs/ONECLICK.md) |
| `ddk change init/reindex/verify/repair/status/export/apply/recover` | Verify existing changes against fixed criteria, inspect evidence, export, apply and recover owned changes |
| `ddk doctor --dry-run` | Read-only readiness check with actual browser/font hashes and installed image digests; `--json` gives structured output |
| `ddk workspace-init` | Create the legacy `.ddk/` workspace; formerly `ddk init PATH` |
| `ddk design new "<idea>"` | Design Studio: turn an idea into design documents |
| `ddk install --all` | Install canonical DDK skills for detected hosts; register MCP where documented |
| `ddk stats --json` | Local cost/usage totals; unknown cost stays null; no source or prompt output |
| `ddk bench --json` | Validate records for the [fixed comparison protocol](benchmarks/PAIRING.md); no model calls |
| `ddk proof`, `ddk audit` | Check capability claims and standards coverage against the evidence on disk |

`run`, `status`, `certify` and `apply` take `--json`. Run `ddk <command> --help` for every option.

The generated [command reference](docs/COMMANDS.md) lists every option.

## Settings

Flags > environment > repository `.env` > `ddk.toml` `[settings]` > defaults.
`ddk config list --repo . --json` reports each value and source with secrets masked.

Set them in the environment or a `.env` file in the working directory.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` or `DDK_ANTHROPIC_API_KEY` | | Anthropic API key for the image workflow and default change repair |
| `DDK_LLM_MODEL` | `claude-sonnet-5-5` | Model for design analysis and code |
| `DDK_LIGHT_MODEL` | `claude-haiku-5-5` | Cheaper model for small steps |
| `DDK_COST_CAP_USD` | `2.0` | Spending limit per run |
| `DDK_VISUAL_CHECK` | `true` | Compare the page with the design |
| `DDK_SSIM_THRESHOLD` | `0.92` | Minimum similarity |
| `DDK_MAX_MISMATCH_RATIO` | `0.03` | Largest share of the page that may differ strongly |
| `DDK_MAX_RETRY_ATTEMPTS` | `3` | Auto-fix rounds (1 to 10) |
| `DDK_INSTALL_DEPENDENCIES` | `false` | Install dependencies in the temporary copy when `node_modules` is missing |
| `DDK_SANDBOX_TIMEOUT_SECONDS` | `300` | Time limit of each build, type-check or lint step |
| `DDK_CHROMIUM_PATH` | | Use this browser instead of looking for one |
| `DDK_LANG` | from your locale | `en` or `ko`; messages follow your locale, English otherwise |
| `DDK_LOG_LEVEL` | `INFO` | Log level |

A browser is found in this order: `DDK_CHROMIUM_PATH`, Playwright's Chromium, then an installed Chrome,
Chromium or Edge.

## What it works with

JavaScript and TypeScript projects with a `package.json`. Build, type-check and lint are detected from
the project's scripts, `tsconfig.json` and ESLint configuration (npm, pnpm, yarn and bun lockfiles are
recognised). The page is previewed with the project's own Vite, Next.js or Astro; other setups can still
be generated and checked, but need `--no-visual` because they cannot be compared in a browser.

## Verify an existing change

`ddk change` checks an explicit baseline and candidate against an approved case and fixed inputs,
without a model or API key. It records requirements, command/test/browser results, environment hashes
and the evidence behind `ready`, `blocked` or `manual-review`.

The default `isolated` execution uses separate app and checker containers on a local Docker daemon,
with prebuilt immutable images. Missing isolation or an environment mismatch blocks the run; it never
falls back to host execution or installs dependencies. Explicit `--trusted-local` runs trusted project
commands with your own permissions. Neither mode proves that an entire application is defect-free.

See the [verified-change guide](docs/VERIFIED-CHANGES.md) for required inputs, execution limits and
managed apply/recovery. This is a separate path from the image-generation loop above. Legacy
`--force`, `--allow-blocked` and whole-repository `ddk rollback` are disabled.

## Agents and MCP

`ddk install --all` installs only detected hosts. Preview with `--dry-run --json`.
`ddk uninstall --host NAME` restores unchanged installed files using `.ddk/install-manifest.json`;
modified files remain as conflicts. Global Claude MCP registration is an explicit owner action.
Global Copilot/Cursor rule installation is unsupported; use project scope or AGENTS.md.
The table records documented formats; interactive host loading remains unverified.
The server provides eleven verified-change tools plus design/preflight/version tools.
Verification stays isolated-only; repair, apply and probe require explicit server-owner and per-call
grants, with an additional grant for host execution. See the [one-command guide](docs/ONECLICK.md). Recovery remains CLI-only.

Image-to-code remains CLI-only:
`ddk run <image> --json` returns the verdict and report path.

## Status

Beta. Automated coverage includes 2,200+ ordinary tests, opt-in headless browser E2E and real local
Docker acceptance tests. Recorded model replies prove the demo flow, not real-model quality on your
project. Actual isolated acceptance has covered macOS ARM64 with OrbStack and a static Node fixture;
other hosts and real Vite/Next.js repositories still need direct evidence.

`ddk change repair` now proposes scoped source fixes and independently rechecks them under one
request budget. It requires explicit provider approval and verified maximum prices; failed or unknown
usage cannot authorize further calls. Next: paid-model repair effectiveness and independent validation
across real projects and operating systems. See the
[roadmap and acceptance criteria](ROADMAP.md). Share a sanitized failing case in an
[issue](https://github.com/dogskip/ddal-ggak/issues); raw reports can contain private project data.

## Develop

```bash
git clone https://github.com/dogskip/ddal-ggak && cd ddal-ggak
uv sync --frozen --extra dev
uv run pytest -m "not playwright and not docker"  # no network, no browser
uv run ruff check src/ tests/ scripts/ && uv run ruff format --check src/ tests/ scripts/ && uv run pyright
DDK_E2E=1 uv run pytest tests/e2e -m playwright    # real npm and Chromium
uv run python scripts/make_readme_assets.py       # rebuild the pictures above
```

See [CONTRIBUTING.md](CONTRIBUTING.md), the [user guide](docs/USER-GUIDE.md), the
[changelog](CHANGELOG.md) and the [roadmap](ROADMAP.md). Public development uses `main`; internal
plans and raw evidence remain local and are excluded from Git and source distributions.

## License

[MIT](LICENSE)

Canonical skills: `ddk-verify` reviews authority and verifies changes, `ddk-evidence` reads bounded evidence and checks current source, and `ddk-design` generates design documents. Invocation names depend on the host format.

<!-- ddk-hosts:start -->
| Host | Project file | Global file | MCP settings |
| --- | --- | --- | --- |
| [claude](https://code.claude.com/docs/en/skills) | `.claude/skills/{name}/SKILL.md` | `.claude/skills/{name}/SKILL.md` | `.mcp.json` |
| [gemini](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/custom-commands.md) | `.gemini/commands/ddk/{short}.toml` | `.gemini/commands/ddk/{short}.toml` | — |
| [opencode](https://opencode.ai/docs/commands/) | `.opencode/commands/{name}.md` | `.config/opencode/commands/{name}.md` | `opencode.json` |
| [codex](https://developers.openai.com/codex/skills) | `.agents/skills/{name}/SKILL.md` | `.agents/skills/{name}/SKILL.md` | `.codex/config.toml` |
| [copilot](https://code.visualstudio.com/docs/copilot/customization/prompt-files) | `.github/prompts/{name}.prompt.md` | unsupported | — |
| [cursor](https://cursor.com/docs/context/rules) | `.cursor/rules/{name}.mdc` | unsupported | `.cursor/mcp.json` |
| [kiro](https://kiro.dev/docs/steering/) | `.kiro/steering/{name}.md` | `.kiro/steering/{name}.md` | — |
<!-- ddk-hosts:end -->
