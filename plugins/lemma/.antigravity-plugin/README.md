# Lemma for Google Antigravity

[Lemma](https://lemma.axiomatic.ai) is [Axiomatic AI](https://axiomatic.ai)'s agent for research
and computing in science and engineering. It works on its own machine, with its own tools, and
keeps a record of every step in a session you can open in the browser.

This plugin lets Antigravity hand work to Lemma. From Antigravity you can start a Lemma session or
resume an earlier one, send it local files, wait in the background for the run to finish, read
Lemma's answer, and download the files it produced. Any session can be opened in the browser to
read the full record or continue the work there.

## Before you install

- **A Lemma account.** Sign up at [lemma.axiomatic.ai](https://lemma.axiomatic.ai).
- **Usage is charged to that account.** Every message Antigravity sends to Lemma starts a run, and
  each run costs the same as a message typed in the browser. Antigravity tells you what it asked
  Lemma to do and gives you a link to the session.
- **Google Antigravity** (the Antigravity app or `agy` CLI) and
  [`uv`](https://docs.astral.sh/uv/getting-started/installation/) on your `PATH`. The plugin runs
  a small local MCP server with `uv`.

## Install

Install from GitHub with `agy`:

```bash
agy plugin install https://github.com/AxiomaticX/lemma-harness-plugins/tree/main/plugins/lemma
```

Restart Antigravity after installing so the `handoff` MCP server loads.

## Sign in

The first time Antigravity uses Lemma, your browser opens to the Lemma sign-in page. Sign in with
your usual Lemma account. The plugin keeps the sign-in in your operating system's keychain, so you
stay signed in across restarts. To sign out, ask Antigravity to sign out of Lemma.

## First use

Ask Antigravity in your own words. For example:

- "Ask Lemma to survey recent literature on perovskite solar cell stability."
- "Send `data/sweep.csv` to Lemma and have it fit the resonance peaks. Download the plots when it
  is done."
- "Have Lemma check the references in `paper.pdf`."
- "Ask Lemma to plan a simulation of this waveguide, but don't run anything until I approve the
  plan."

Antigravity writes the brief for Lemma, sends it, gives you the session link, and starts
`wait_for_result` in the background. Runs take minutes, and long ones take hours. You can keep
working in the meantime: Antigravity is woken when the run ends (or after `wake_after_minutes`, 60
by default) and reports what Lemma answered.

## What you can do

- **Hand over a task.** Start a session with the goal, context, and any local files you name, or
  continue an existing session with follow-up messages.
- **Pick up earlier sessions.** Search your past Lemma sessions by keyword or list recent ones,
  read their transcripts, and continue them.
- **Use a ready-made workflow.** List Lemma's workflows (literature survey, interactive paper,
  reference verification, device simulation, and more) and run one with your inputs and files.
- **Plan before running.** In plan mode, Lemma drafts a plan with tasks and questions, and nothing
  runs until you approve it. Answer questions, edit tasks, run one task or all of them, and review
  finished tasks.
- **Answer Lemma's questions.** When Lemma stops for a decision, Antigravity puts the question to
  you and acts only on your answer.
- **Bring results back.** List the files in a session and download the ones you want. Downloads
  never overwrite an existing local file.
- **Open the session in the browser.** Ask Antigravity to open any session to read every step,
  view notebooks, or continue the work in Lemma.

## Settings

Ask Antigravity to configure Lemma—for example, "configure Lemma not to open the browser" or
"configure Lemma to use the GPU machine by default". That calls the `configure` tool, applies the
change immediately without restarting, and saves it to `~/.lemma-mcp/config.json` (mode `0600`) so
it survives plugin updates.

| Setting | Default | Values |
| --- | --- | --- |
| `open_browser` | `true` | `true` or `false` — opens each new session in your browser when the first message is sent. |
| `default_model` | `Lemma's default` | `Lemma's default`, `Anthropic · Pro Fast`, `Anthropic · Pro`, `Anthropic · Normal`, `Google · Pro`, `Google · Normal`, `Open-weight · Pro`, `Open-weight · Normal`. |
| `default_machine` | `Standard` | `Standard`, `Enhanced`, `High performance`, `Max`, `GPU`. Larger machines cost more and cannot change once a session starts. |

You can also override settings from the environment that starts Antigravity with
`LEMMA_OPEN_BROWSER`, `LEMMA_DEFAULT_MODEL`, `LEMMA_DEFAULT_MACHINE`, and
`LEMMA_MAX_TOOL_OUTPUT_CHARS` (default `40000`).

## Your data and local file access

- Files are sent from, and saved to, the open workspace (the folders Antigravity reports over MCP)
  and any folders listed in `LEMMA_ALLOWED_DIRS` (separated by `:`).
- For any other path, Antigravity asks you to allow it first; the agent cannot answer for you.
- Hidden files and folders (such as `.env`, `.ssh`, or `.aws`) are always refused.
- The sign-in is stored in your operating system's keychain under `axiomatic-lemma`. Signing out
  removes it.

## What the plugin runs, sends, and fetches

- **Runs locally:** the `lemma-mcp` stdio MCP server (`server/`), started with `uv` when the
  plugin loads.
- **Fetches on first start of each plugin version:** `uv` installs pinned Python runtime
  dependencies from PyPI (`server/uv.lock`), and downloads Python 3.12+ if none is installed.
- **Sends to Lemma:** over HTTPS to `api.axiomatic-ai.com`, the messages, settings, and answers
  passed to Lemma's tools, plus any files you name (uploaded to the presigned storage link Lemma
  returns).
- **Signs in with:** `auth.axiomatic-ai.com` via your browser (PKCE on a local `127.0.0.1`
  callback on the first free port of `47815`, `47816`, or `47817`).
- **Writes locally:** files you download or save with `output_file`, the refresh token in the OS
  keychain, `~/.lemma-mcp/config.json` and the sign-in lock file in `~/.lemma-mcp`, and the Python
  environment in `uv`'s cache and `server/.venv`.

Nothing else is sent anywhere.

## Update or remove

```bash
agy plugin uninstall lemma
agy plugin install https://github.com/AxiomaticX/lemma-harness-plugins/tree/main/plugins/lemma
```

Restart Antigravity afterwards. You stay signed in to Lemma and your saved `~/.lemma-mcp/config.json`
settings are preserved.

## Support

Email [developers@axiomatic-ai.com](mailto:developers@axiomatic-ai.com).
