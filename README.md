# ddalggak

**Design image in. Checked code out.**

[![CI](https://github.com/dogskip/ddal-ggak/actions/workflows/ci.yml/badge.svg)](https://github.com/dogskip/ddal-ggak/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

English · [한국어](README.ko.md)

`ddk` turns a design image into code for your own repository, then checks its own work. It builds the
project, type-checks and lints it, renders the page in a real headless browser, compares the
screenshot with your design, repairs what differs, and only then says whether the result is safe to
apply. Nothing is written to your repository until you run `ddk apply`.

![The design, the first generated attempt, the difference in red, and the page after auto-fix](docs/assets/before-after.png)

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
  (`npm`, `pnpm`, `yarn`, `bun`, `npx`, `node`, `tsc`, `vite`, `git`).
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
| `ddk apply` | Write the files of a `ready` case into the repository (`--dry-run`, `--force`, `--allow-blocked`) |
| `ddk status`, `ddk certify` | The saved state and verdict of a case |
| `ddk rollback` | Reset the repository to the git checkpoint of a repair round (`git reset --hard`; read the user guide first) |
| `ddk doctor` | Check Python, uv, API key, Node.js, git, Chromium (`--install-browser` downloads it) |
| `ddk design new "<idea>"` | Design Studio: turn an idea into design documents |
| `ddk install --all` | Register `/ddk:design` and the MCP server with Claude Code, Cursor, Codex, Gemini CLI and others |
| `ddk proof`, `ddk audit` | Check capability claims and standards coverage against the evidence on disk |

`run`, `status`, `certify` and `apply` take `--json`. Run `ddk <command> --help` for every option.

## Settings

Set them in the environment or a `.env` file in the working directory.

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` or `DDK_ANTHROPIC_API_KEY` | | Anthropic API key (the only provider so far) |
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

## Agents and MCP

`ddk install --all` adds the `/ddk:design` command and an MCP server to the AI coding tools it finds.
Both cover **Design Studio** (idea to design documents). The image-to-code loop is CLI-only today; an
agent can call `ddk run <image> --json` from its shell tool and read the report path from the result.

## Status

Beta. The loop is exercised end to end by `ddk demo` and by a test suite of 1,600+ tests that use
scripted model replies and, optionally, a real browser. How good the code is on your designs depends on
the model and on the design, and the real-model path has seen far less use than the demo: expect rough
edges and please [open an issue](https://github.com/dogskip/ddal-ggak/issues) with the report of a bad
case. Not there yet: image-to-code through MCP, preview servers beyond Vite, Next.js and Astro, and
comparing more than one image.

## Develop

```bash
git clone https://github.com/dogskip/ddal-ggak && cd ddal-ggak
uv sync --extra dev
uv run pytest -m "not playwright"                  # no network, no browser
uv run ruff check . && uv run ruff format --check . && uv run pyright
DDK_E2E=1 uv run pytest tests/e2e -m playwright    # real npm and Chromium
uv run python scripts/make_readme_assets.py       # rebuild the pictures above
```

See [CONTRIBUTING.md](CONTRIBUTING.md), the [user guide](docs/USER-GUIDE.md), the
[changelog](CHANGELOG.md) and the [design documents](docs/design/00-document-inventory.md).

## License

[MIT](LICENSE)
