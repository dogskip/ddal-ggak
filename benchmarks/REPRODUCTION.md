# Repository reproduction checks

The reproduction suite runs three fixed, synthetic Git repositories through the real CLI and
headless Chromium. Each repository has an independently specified browser target, preservation
checks, and native tests. It records expected rejections separately from failures of the suite.

| Repository | Requested change | Preserved behavior | Native report |
| --- | --- | --- | --- |
| Python service | A two-item discounted order totals 18.00 | Standard price and empty orders | Python `unittest` counts in `ddk-json` |
| JavaScript module | ` Hello World ` becomes `hello-world` | Empty and already normalized input | Node `node:test` JUnit XML |
| Browser counter | Add one increases the count by one | Reset returns zero | Node `node:test` JUnit XML plus browser clicks |

Sources live in [tests/fixtures/reproduction](../tests/fixtures/reproduction). Each run creates a
private Git repository, commits the baseline and applies one explicit test mutation. The three
variants are a valid change, a missed target, and a regression of preserved behavior. A successful
matrix contains six `ready` runs and twelve correctly `blocked` runs across the two runtimes.
Those counts are the required matrix, not a measured repair success rate.

The [recorded installed-wheel run](reproduction-results.json) matched all eighteen expected
decisions with zero skips and zero model calls. It identifies the base commit, the uncommitted
runtime update by SHA-256, the tested wheel and each case's environment. These are local results
for the recorded synthetic examples.

## Runtime scope

- `host` executes in a private source copy with host permissions and explicit `trusted-local`
  authority. It uses installed Python, Node and headless Chromium.
- `isolated` executes the app and browser observer in separate Linux Docker containers with
  immutable local image IDs. The coordinating CLI can still run on macOS. This is not evidence
  of a native Linux installation or GitHub Actions execution.
- The Python example serves its real calculation over HTTP. The JavaScript example similarly
  exposes its real module output. Command-only target/preserve checks do not satisfy the current
  bootstrap acceptance contract, which requires browser or visual checks.
- The dependency-free examples use an empty lockfile marker for the existing isolated environment
  contract. They do not test npm installation, dependency resolution or lifecycle scripts.

Case preparation calls `CaseBootstrapper` with the observed environment. Verification, replay and
current-source gates use the CLI. Isolated cases are explicitly prepared; this does not add automatic
isolated bootstrap to `ddk init` or establish first-use success for `ddk up`.

## Execution and evidence

Use the development dependencies from `uv.lock` and installed browser binaries. The suite does not
install browsers, fetch images, invoke a model, enable CI, or modify the source repository's hooks.

```sh
uv run python scripts/check_reproducibility.py --runtime host --out evidence/reproduction-host
```

The full matrix also requires `DDK_APP_IMAGE` and `DDK_CHECKER_IMAGE`, each set to an existing
`sha256:...` image ID. The app image must contain Python 3.12, Node and npm. The checker image must
contain the existing verified worker's dependencies, sandbox-capable Chromium and fonts.
[app.Dockerfile](../tests/fixtures/reproduction/app.Dockerfile) combines an already prepared checker
image with an already prepared Node image. Supply `NODE_IMAGE` and `CHECKER_IMAGE` build arguments;
build with `--network=none --pull=false` and verify both local base IDs. Record the resulting image
ID rather than passing a mutable tag to the evaluator.

```sh
uv run python scripts/check_reproducibility.py --out evidence/reproduction-all
```

The output directory must not exist. A failed attempt remains intact for comparison with a new
attempt. Output includes:

- `inputs.json`: SHA-256 of the runner, matrix definitions and fixture sources.
- `pytest.xml` and `pytest.txt`: every executed test, failure and skip.
- `runs/`: CLI results and canonical Case/Run files with native logs, report bytes, screenshots,
  browser observations, environment records and cleanup evidence.
- `receipts/`: verified source preservation, decisions, replay, gate, elapsed time and model cost.
- `summary.json`: incomplete matrices, duplicated rows, unexpected decisions, skips, unknown costs
  or failed integrity checks force `status=failed` and a nonzero process exit.

`--installed` requires `ddk` to come from the invoking Python environment's installed distribution,
disables the test configuration's `src` import path, and checks the actual imported package path.
Install the wheel and locked test dependencies in a separate environment before using this option.
The environment still needs the repository's test files; this is an installation check conducted by
the maintainer, not an independent first-time-user study.

All browser actions run headless. Verification checks both the baseline and candidate, verifies
artifact hashes and cleanup, and replays the saved decision without another execution. A passing
current-source gate is required for valid changes. Expected rejected variants must also replay as
`blocked`; exit zero from replay alone is insufficient.

## Interpreting results

The suite measures reproducibility of its frozen acceptance checks. It does not supply a calibrated
representative-project corpus, real-world failure rate, paid-model repair rate, independent user
success, comparative rank or a latency guarantee. `repair_success_rate` and
`independent_user_success_rate` remain `null`. Model API cost is zero only because each saved Run
must contain zero model calls; machine time and other infrastructure costs are not priced.

Raw evidence stays local under an ignored output directory. Any public result must omit local paths,
credentials and private project material, and identify the runtime and source hashes used.
