# Browser Case drafts

These are functional test fixtures, labeled **draft without direction**, with ENERGY 1 /
RHYTHM 1 / MOTION 1. They are not a product design. Each page exposes actual candidate behavior
so that the existing immutable browser criteria can observe it without changing the Case contract.

| Task | Browser target | Browser preservation | Independent additional coverage |
| --- | --- | --- | --- |
| Click | `/target` displays `name.txt` from the candidate formatter | `/preserve` retains `/scope/name.txt` | Invalid UTF-8 bytes and native full-path formatting |
| clsx | Truthy object flags produce `active` | Strings and nested arrays produce `x y` | Falsy omission and mixed nested object/array inputs |
| Hyperapp | Add one changes 0 to 1; Reset changes 1 to 0 | Initial heading is Counter and initial value is 0 | Repeated increments and reset in a fresh browser |

The helper program is fixed outside the one-file change scope. Its exact bytes are included in
both arms before Git freezes the initial tree. Click imports from the candidate's `src` directory
and asserts that location; browser modules are served only from the selected candidate paths.
The HTTP server binds loopback and has an explicit route allowlist. It installs no dependencies.
Candidate code still requires a separate trusted-local grant and retains host permissions.

## Reviewable hashes

Preparation records three draft hashes; an owner must review the corresponding complete JSON,
not approve a displayed status alone. For the current drafts:

| Draft | SHA-256 |
| --- | --- |
| `click-short-name.json` | `e320830977b198ae49ce34a2b53173c34a4cb2d1c15577f4bb51b2b11def7aac` |
| `clsx-object-flags.json` | `44eebe5bb891c1538f9ef43b7bed0c4674cae3661185d8244366e910da59834b` |
| `hyperapp-events.json` | `ae7d2f242cf4e30dd2d865bf23488542fe9c9faceb20e17fd5ad970188da2287` |

The default DDK repair attempts, provider requests and budget are zero. Model-host usage is a
separate experimental cost and requires its own limits. A reviewed draft hash is not a model,
execution or publication grant. The [protocol](PAIRING.md) specifies how one sealed Case is
shared across the three independent DDK directories. User comparison inputs remain unsealed.

## Fixture direction

- Black text and boundaries on white keep contrast fixed at 21:1 for reproducible observation.
  A theme switch would add an unrelated experimental variable, so this test surface fixes light.
- System text avoids font downloads; the existing Case records pin host fonts and the browser.
- One heading and one result keep the observed behavior visible. The counter adds only its two
  native actions, with 44 px targets, keyboard operation and explicit visible focus.
- Flexible text and default flow fit narrow viewports. The 1 rem margin and result spacing keep
  controls separate without creating a layout dependency.
- There are no marketing claims, illustrations, icons, cards, navigation or animations. Counter
  values are actual application state, not performance statistics. Module loading and failure
  messages identify unavailable candidate behavior; they cannot satisfy the target criteria.

## Local evidence

Preparation, sealing and verification are local engineering checks. They do not measure model
repair success, costs or DDK's comparative effect. Original, manually restored and deliberately
regressed candidates are kept separate from the unmeasured 18-episode comparison input.
The calibrated baseline remains false. Detailed receipts and the final acceptance results are
recorded in [the execution report](../docs/HARNESS-EXECUTION.md).

## Draft UI delivery check

Evidence: the fixture source, its nine viewport screenshots and DOM checks in
`/tmp/ddk-harness-work/p2-case-browser-review/summary.json`, controlled module-state checks in
`states.json`, and the Python fixture tests. This check applies to an explicitly labeled functional
draft; it does not approve a product visual identity.

| Rule | Result | Evidence |
| --- | --- | --- |
| R-01 | PASS | No gradients or decorative color effects in the fixture source. |
| R-02 | PASS | Fixture copy contains no em dash. |
| R-03 | PASS | All three tasks fit 320, 768 and 1280 px without overflow; targets are at least 44 px. |
| R-04 | PASS | No feature icons. |
| R-05 | PASS | One functional result per page; declared uniform rhythm fits a test fixture. |
| R-06 | PASS | System text avoids downloads and matches the recorded host environment. |
| R-07 | PASS | No background pattern. |
| R-08 | PASS | Buttons use action labels without decorative arrows. |
| R-09 | PASS | No badges. |
| R-10 | PASS | No blur or translucent surfaces. |
| R-11 | PASS | Only native action buttons have a small 2 px radius. |
| R-12 | PASS | No shadows. |
| R-13 | PASS | No glow. |
| R-14 | PASS | No feature cards. |
| R-15 | PASS | Add one and Reset describe their verified actions. |
| R-16 | PASS | No marketing claims or buzzwords. |
| R-17 | PASS | Displayed counter values are observed native application state. |
| R-18 | PASS | No testimonials. |
| R-19 | PASS | No animations; MOTION 1 is explicit. |
| R-20 | PASS | Filename, Classes and Counter identify each actual interface; visual direction remains draft. |
| R-21 | PASS | Fixed light colors remove an unrelated experimental variable, as documented above. |
| R-22 | PASS | No illustrations. |
| R-23 | PASS | No identity assets or invented navigation; every page displays its draft label. |
| R-24 | PASS | No navigation links. |
| R-25 | PASS | Computed black text, borders and focus on white have 21:1 contrast. |
| R-26 | PASS | Add one changes 0 to 1; Reset returns 1 to 0 at all tested widths. |
| R-27 | PASS | Empty/failure Python cases and controlled JS loading/empty/failure states were observed. |
| R-28 | PASS | No FAQ. |
| R-29 | PASS | Black and white only. |
| R-30 | PASS | No product imitation; composition follows the native functions under test. |
| R-31 | PASS | Color, type, layout and spacing reasons are recorded above. |
| R-32 | PASS | Tab, Shift+Tab, Enter and Space operate both controls; focused outline is 3 px. |
| R-33 | PASS | HTML is authored directly in the fixture asset; controlled source mutations are benchmark data. |
| R-34 | PASS | One fixed theme with computed contrast and viewport checks. |
| R-35 | PASS | Nine real headless pages, all controls exercised, zero normal console/page errors. |
| R-36 | PASS | No unsupported security, speed, cost or comparative effectiveness claims. |
| R-37 | PASS | Every page says draft without direction; all three declared dials are 1. |
| R-38 | PASS | All result text comes from actual or explicitly controlled test code. |
