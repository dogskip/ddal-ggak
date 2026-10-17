---
name: verify
description: Verify repository changes against target and preserve checks using DDK evidence. Use before claiming that an implementation works or applying a change.
---

Clarify the requested behavior and the behavior that must be preserved. Reuse existing code and
standard platform features before adding dependencies or abstractions. Keep the proposed change
small. A model's explanation is never evidence of completion.

First request a read-only execution plan:

```bash
ddk up "<request>" --repo "<repo>" --dry-run --json
```

Inspect status and actions even when the command exits zero. When a response has `data`, that
field contains the verification record. Show the plan and unresolved target/preserve checks to
the user. Missing acceptance criteria must be reviewed before execution.

Obtain explicit approval for execution with host permissions before using this command:

```bash
ddk up "<request>" --repo "<repo>" --trusted-local --json
```

Never add `--trusted-local` without that approval. Never add `--repair --confirm-provider`
without separate provider-transfer approval and a budget. Never add `--apply` without explicit
application approval and the required confirmations. A task request alone does not grant these
capabilities. Do not invent criteria to make a failing result pass.

Read decision and actions from the saved verification record. If decision is not ready, report
its actions unchanged; stop at the missing capability or failed check. Report ready only when
DDK's hard checks and evidence establish it, and confirm the current-source gate before applying.
Details: [approval and evidence boundaries](references/ddk-verify.md).
