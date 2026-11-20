# Axiomatic harness plugins

Plugins that let agent harnesses use Axiomatic products. This repository is also the
`axiomatic-ai` Claude Code marketplace.

| Plugin | What it does |
| --- | --- |
| `axiomaticai` | Hand a task to Lemma from Claude Code or Google Antigravity: start a conversation, send local files, wait for the run, read the answer, download results, open the conversation in the browser, and search and read earlier conversations. |

## Install

Requires [`uv`](https://docs.astral.sh/uv/) on `PATH`.

### Claude Code

Requires Claude Code. Paste this into Claude Code:

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

### Google Antigravity

Requires Google Antigravity (`agy` CLI or Antigravity App). Install from GitHub:

```
agy plugin install https://github.com/AxiomaticX/axiomatic-harness-plugins/tree/main/plugins/axiomaticai
```

Or install from a local checkout:

```
agy plugin install /path/to/axiomatic-harness-plugins/plugins/axiomaticai
```

Antigravity stages the plugin into `~/.gemini/config/plugins/axiomaticai/` (or place it in
`.agents/plugins/axiomaticai/` for a single workspace). By default it talks to production Lemma,
opens each new conversation in the browser, and uses Lemma's default model and `Standard`
machine.

To change settings in Antigravity, ask the agent to configure Lemma (for example, *"configure
Lemma to use staging and don't open the browser"*). That calls the `configure` tool, applies
immediately without restarting, and saves to `${PLUGIN_DATA}/config.json` so settings survive
plugin updates:

- `environment`: `production` (default), `staging`, or `dev`
- `open_browser`: `true` (default) or `false`
- `default_model`: `Lemma's default`, `Anthropic · Pro Fast`, `Anthropic · Pro`,
  `Anthropic · Normal`, `Google · Pro`, `Google · Normal`, `Open-weight · Pro`, or
  `Open-weight · Normal`
- `default_machine`: `Standard`, `Enhanced`, `High performance`, `Max`, or `GPU`

You can also edit `config.json` directly, or override any setting via `LEMMA_ENVIRONMENT`,
`LEMMA_OPEN_BROWSER`, `LEMMA_DEFAULT_MODEL`, or `LEMMA_DEFAULT_MACHINE` in `mcp_config.json`.

### Which local files Lemma can reach

Files are sent from, and saved to, the open workspace (the folders the harness reports over MCP),
the project (`CLAUDE_PROJECT_DIR` in Claude Code), and any folders listed in `LEMMA_ALLOWED_DIRS`
(separated by `:`). For any other path, the harness asks you to allow it first; the agent cannot
answer for you, and a harness that cannot ask refuses the path. Hidden files and folders, such as
`.env`, `.ssh` or `.aws`, are always refused. The agent cannot change `LEMMA_ALLOWED_DIRS`; set
it in the environment that starts the harness.

## Sign in

The first Lemma tool call opens the browser to sign in to Lemma with your usual account. The
sign-in is kept in the OS keychain and refreshed automatically, so it survives restarts. Call
the `logout` tool to remove it.

Sign-in listens for the browser's redirect on `127.0.0.1`, on the first free port of 47815,
47816 and 47817.

## What the plugin contains

`plugins/axiomaticai/`:

- `.claude-plugin/plugin.json` and `.antigravity-plugin/plugin.json`: plugin manifests for Claude
  Code and Google Antigravity.
- `.mcp.json` (Claude Code) and `mcp_config.json` (Antigravity): a local stdio MCP server, run
  with `uv` from `server/`. Its virtualenv lives in the plugin's data directory, so plugin
  updates don't rebuild it in place. In Antigravity, `wait_for_result` is configured to run in
  the background (`"background": "always"`, `"timeoutSeconds": -1`) and wake the agent when the
  run ends.
- `hooks/hooks.json` (Claude Code): after `send_message` or a `wait_for_result` that found the
  run still going, a background hook waits on the run and wakes Claude when it ends, or after
  `wake_after_minutes` (60 by default) to say it is still running. Nothing runs while you aren't
  using Lemma.
- `skills/lemma/SKILL.md`: how an agent should work with Lemma.
- `assets/logo.svg`: plugin icon for Antigravity.
- `server/`: the `lemma-mcp` server and the `lemma-wake` hook, in one Python package.

All file transfer goes through `server/src/lemma_mcp/client/files.py`.

## Develop

```
cd plugins/axiomaticai/server
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

From the repository root, check the manifests:

```
claude plugin validate --strict plugins/axiomaticai
claude plugin validate --strict .
agy plugin validate plugins/axiomaticai
```

To try a local checkout in Claude Code, add the repository directory as a marketplace:

```
/plugin marketplace add /path/to/axiomatic-harness-plugins
/plugin install axiomaticai@axiomatic-ai
```

To try a local checkout in Antigravity (remove `plugins/axiomaticai/server/.venv` first if you
ran `uv sync` locally, as `agy plugin install` rejects symlinks pointing outside the plugin
directory):

```
agy plugin install /path/to/axiomatic-harness-plugins/plugins/axiomaticai
```
