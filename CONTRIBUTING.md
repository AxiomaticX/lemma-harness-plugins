# Contributing

This repository is the `axiomatic-ai` Claude Code marketplace, and holds the same plugin for
Google Antigravity. It holds one plugin, `lemma`, in `plugins/lemma/`. Its skill and MCP server
are also named `lemma`. Users call the skill as `/lemma`; its full name in Claude Code is
`lemma:lemma`.

## What the plugin contains

- `.mcp.json`: a local stdio MCP server, run with `uv` from `server/`.
- `.antigravity-plugin/plugin.json` and `mcp_config.json`: the Antigravity manifest and its MCP
  server, which sets `LEMMA_HARNESS=antigravity` and runs `wait_for_result` in the background
  with no timeout, since Antigravity has no wake-up hook.
- `README.md` and `LICENSE`: the user guide and license the plugin directory reads from this
  folder.
- `hooks/hooks.json`: after `send_message` or a `wait_for_result` that found the run still going,
  a background hook waits on the run and wakes Claude when it ends, or after
  `wake_after_minutes` (60 by default) to say it is still running. Nothing runs while Lemma is
  not in use.
- `skills/lemma/SKILL.md`: how an agent should work with Lemma.
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

In Antigravity, check the manifest and install a local checkout. Remove `server/.venv` first if
you ran `uv sync`, as `agy plugin install` rejects symlinks that point outside the plugin folder:

```bash
agy plugin validate plugins/lemma
agy plugin install /path/to/lemma-harness-plugins/plugins/lemma
```
