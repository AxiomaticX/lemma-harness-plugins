# Lemma harness plugins

Plugins that let agent harnesses use Axiomatic products. This repository is also the
`axiomatic-ai` Claude Code marketplace.

| Plugin | What it does |
| --- | --- |
| `axiomaticai` | Hand a task to Lemma from Claude Code: start a conversation or find and read an earlier one, send local files, wait for the run, read the answer, download results, and open the conversation in the browser. |

## Install

Requires Claude Code and [`uv`](https://docs.astral.sh/uv/) on `PATH`. Paste this into Claude Code:

```
Install the Lemma plugin from the AxiomaticX/axiomatic-harness-plugins marketplace.

First ask me two questions, and wait for both answers:
1. Install it for my user (every project) or for this project only?
2. Should each new Lemma conversation open in my browser when a message is sent? It is on unless I say no.

Then, with SCOPE as user or project from my first answer and OPEN as true or false from my second, run:

claude plugin marketplace add AxiomaticX/axiomatic-harness-plugins --scope SCOPE
claude plugin install axiomaticai@axiomatic-ai --scope SCOPE --config open_browser=OPEN

Report each command's output, then tell me to run /reload-plugins to load it.
```

Or by hand, in Claude Code:

```
/plugin marketplace add AxiomaticX/axiomatic-harness-plugins
/plugin install axiomaticai@axiomatic-ai
```

The install asks whether to open each new conversation in the browser (on by default). Change
it later with `/plugin configure axiomaticai@axiomatic-ai`.

The plugin talks to production Lemma. To use staging or dev, set its `environment` option to
`staging` or `dev` with `/plugin configure axiomaticai@axiomatic-ai`, or install with
`--config environment=staging`.

## Sign in

The first Lemma tool call opens the browser to sign in to Lemma with your usual account. The
sign-in is kept in the OS keychain and refreshed automatically, so it survives restarts. Call
the `logout` tool to remove it.

Sign-in listens for the browser's redirect on `127.0.0.1`, on the first free port of 47815,
47816 and 47817.

## What the plugin contains

`plugins/axiomaticai/`:

- `.mcp.json`: a local stdio MCP server, run with `uv` from `server/`. Its virtualenv lives in
  the plugin's data directory, so plugin updates don't rebuild it in place.
- `hooks/hooks.json`: after `send_message` or a `wait_for_result` that found the run still going,
  a background hook waits on the run and wakes Claude when it ends, or after
  `wake_after_minutes` (60 by default) to say it is still running. Nothing runs while you aren't
  using Lemma.
- `skills/lemma/SKILL.md`: how an agent should work with Lemma.
- `server/`: the `lemma-mcp` server and the `lemma-wake` hook, in one Python package.

All file transfer goes through `server/src/lemma_mcp/client/files.py`.

## Develop

```
cd plugins/axiomaticai/server
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

From the repository root, check both manifests:

```
claude plugin validate --strict plugins/axiomaticai
claude plugin validate --strict .
```

To try a local checkout, add the repository directory as a marketplace:

```
/plugin marketplace add /path/to/axiomatic-harness-plugins
/plugin install axiomaticai@axiomatic-ai
```
