# Quick start

```bash
# 1. See the whole loop work, no API key (needs uv, Node.js and a Chrome, Edge or Chromium)
uvx --from git+https://github.com/dogskip/ddal-ggak ddk demo

# 2. Install it
uv tool install git+https://github.com/dogskip/ddal-ggak
ddk doctor                                   # what is missing on this machine

# 3. Run it on your design, inside a repository with a package.json and installed dependencies
export ANTHROPIC_API_KEY=sk-ant-...
ddk run design.png

# 4. Read why it decided what it decided
ddk report --open

# 5. Write the files into your repository (only a `ready` case; --dry-run shows the plan)
ddk apply
```

The [README](../README.md) explains what each step does and what the check can and cannot see; the
[user guide](USER-GUIDE.md) covers preparing a repository, reading the report, steering a run and
fixing common problems. Korean: [README.ko.md](../README.ko.md), [USER-GUIDE.ko.md](USER-GUIDE.ko.md).
