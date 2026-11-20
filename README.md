# Lemma harness plugins

Plugins that let agent harnesses use Axiomatic products. This repository is also the
`axiomatic-ai` Claude Code marketplace.

| Plugin | What it does |
| --- | --- |
| `axiomaticai` | Hand a task to Lemma from Claude Code: start a conversation, send local files, wait for the run, read the answer, download results, and open the conversation in the browser. |

## Install

Requires Claude Code and [`uv`](https://docs.astral.sh/uv/) on `PATH`. Paste this into Claude Code:

```
Install the Lemma plugin from the AxiomaticX/lemma-harness-plugins marketplace.

First ask me two questions, and wait for both answers:
1. Install it for my user (every project) or for this project only?
2. Should each new Lemma conversation open in my browser when a message is sent? It is on unless I say no.

Then, with SCOPE as user or project from my first answer and OPEN as true or false from my second, run:

claude plugin marketplace add AxiomaticX/lemma-harness-plugins --scope SCOPE
claude plugin install axiomaticai@axiomatic-ai --scope SCOPE --config open_browser=OPEN

Report each command's output, then tell me to run /reload-plugins to load it.
```

Or by hand, in Claude Code:

```
/plugin marketplace add AxiomaticX/lemma-harness-plugins
/plugin install axiomaticai@axiomatic-ai
```

The install asks whether to open each new conversation in the browser (on by default). Change
it later with `/plugin configure axiomaticai@axiomatic-ai`.

## Which local files Lemma can reach

Files are sent from, and saved to, the open workspace (the folders Claude Code reports over MCP),
the project (`CLAUDE_PROJECT_DIR`), and any folders listed in `LEMMA_ALLOWED_DIRS` (separated by
`:`). For any other path, Claude Code asks you to allow it first; Claude cannot answer for you.
Hidden files and folders, such as `.env`, `.ssh` or `.aws`, are always refused. Claude cannot
change `LEMMA_ALLOWED_DIRS`; set it in the environment that starts Claude Code.

## Sign in

The first Lemma tool call opens the browser to sign in to Lemma with your usual account. The
sign-in is kept in the OS keychain and refreshed automatically, so it survives restarts. Call
the `logout` tool to remove it.

Sign-in listens for the browser's redirect on `127.0.0.1`, on the first free port of 47815,
47816 and 47817.

## What the plugin runs, sends and fetches

- **Runs locally:** the `lemma-mcp` server, started by Claude Code when the plugin loads, and the
  `lemma-wake` hook, started after a Lemma tool call that leaves a run going. Both are the Python
  in `plugins/axiomaticai/server/`, run with `uv`.
- **Fetches on first start:** `uv` installs the server's dependencies from PyPI, pinned by
  `server/uv.lock`.
- **Sends to Lemma:** over HTTPS to `api.axiomatic-ai.com`, the messages, settings and answers
  Claude passes to Lemma's tools, and the files you name in them. Files go to the storage link
  Lemma returns for each upload, and downloads come from the storage link Lemma returns for each
  file.
- **Signs in with:** `auth.axiomatic-ai.com`, through your browser. The refresh token is kept in
  the OS keychain and sent only to `auth.axiomatic-ai.com`.
- **Opens in your browser:** the sign-in page, and each new conversation on `lemma.axiomatic.ai`
  unless you turned that off.
- **Writes locally:** files you ask Claude to download, into the folders listed under "Which local
  files Lemma can reach", and a lock file in the plugin's data directory.

Nothing else is sent anywhere, and nothing runs while you aren't using Lemma.

## What the plugin contains

`plugins/axiomaticai/`:

- `.mcp.json`: a local stdio MCP server, run with `uv` from `server/`. Its virtualenv is
  `server/.venv` in the installed plugin, shared with the hook and rebuilt for each plugin version.
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
/plugin marketplace add /path/to/lemma-harness-plugins
/plugin install axiomaticai@axiomatic-ai
```
