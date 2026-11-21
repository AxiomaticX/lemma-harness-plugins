# Contributing

This repository is the `axiomatic-ai` marketplace for Claude Code and OpenAI Codex. It holds one
plugin, `lemma`, in `plugins/lemma/`. Its skill and MCP server are both named `handoff`, so they
show in Claude Code as `lemma:handoff`.

## What the plugin contains

- `.mcp.json`: a local stdio MCP server, run with `uv` from `server/`.
- `plugin.json` and `mcp.json`: the Codex manifest (Agent Plugins format) and its MCP server,
  which sets `LEMMA_HARNESS=codex` so `wait_for_result` waits in 240-second calls instead of
  relying on the wake-up hook. `.codex-plugin/plugin.json` forwards the `LEMMA_*` settings and
  the keychain and browser variables from Codex's environment, and is the manifest for Codex
  versions without Agent Plugins support. Both turn off `hooks/hooks.json` in Codex.
- `../../.agents/plugins/marketplace.json`: the Codex marketplace catalog.
- `README.md` and `LICENSE`: the user guide and license the plugin directory reads from this
  folder.
- `hooks/hooks.json`: after `send_message` or a `wait_for_result` that found the run still going,
  a background hook waits on the run and wakes Claude when it ends, or after
  `wake_after_minutes` (60 by default) to say it is still running. Nothing runs while Lemma is
  not in use.
- `skills/handoff/SKILL.md`: how an agent should work with Lemma.
- `server/`: the `lemma-mcp` server and the `lemma-wake` hook, in one Python package.

All file transfer goes through `server/src/lemma_mcp/client/files.py`.

## Develop

```bash
cd plugins/lemma/server
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

From the repository root, check both manifests:

```bash
claude plugin validate --strict plugins/lemma
claude plugin validate --strict .
```

To try a local checkout, add the repository directory as a marketplace:

```
/plugin marketplace add /path/to/lemma-harness-plugins
/plugin install lemma@axiomatic-ai
```
