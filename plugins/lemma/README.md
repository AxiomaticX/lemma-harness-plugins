# Lemma for Claude Code

[Lemma](https://lemma.axiomatic.ai) is [Axiomatic AI](https://axiomatic.ai)'s agent for research and
computing in science and engineering. It works on its own machine, with its own tools, and keeps a record of
every step in a session you can open in the browser.

This plugin lets Claude Code hand work to Lemma. From Claude Code you can start a Lemma session,
send it local files, wait for the run to finish, read Lemma's answer, and download the files it
produced. Any session can be opened in the browser to read the full record or to continue the
work there.

## Before you install

- **A Lemma account.** Sign up at [lemma.axiomatic.ai](https://lemma.axiomatic.ai).
- **Usage is charged to that account.** Every message Claude sends to Lemma starts a run, and
  each run costs the same as a message typed in the browser. Claude tells you what it asked
  Lemma to do and gives you a link to the session.
- **Claude Code**, and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) on your
  `PATH`. The plugin runs a small local server with `uv`.

## Install

In Claude Code, run:

```
/plugin marketplace add AxiomaticX/lemma-harness-plugins
/plugin install lemma@axiomatic-ai
/reload-plugins
```

The install asks whether each new Lemma session should open in your browser when Claude sends
it a message. The default is yes.

To install from a terminal instead, for every project (`user`) or for one project (`project`):

```bash
claude plugin marketplace add AxiomaticX/lemma-harness-plugins --scope user
```

```bash
claude plugin install lemma@axiomatic-ai --scope user
```

## Sign in

The first time Claude uses Lemma, your browser opens to the Lemma sign-in page. Sign in with
your usual Lemma account. The plugin keeps the sign-in in your operating system's keychain, so
you stay signed in across restarts. To sign out, ask Claude to sign out of Lemma.

## First use

Ask Claude in your own words. For example:

- "Ask Lemma to survey recent literature on perovskite solar cell stability."
- "Send `data/sweep.csv` to Lemma and have it fit the resonance peaks. Download the plots when
  it is done."
- "Have Lemma check the references in `paper.pdf`."
- "Ask Lemma to plan a simulation of this waveguide, but don't run anything until I approve the
  plan."

To make sure Claude uses Lemma, start the request with `/lemma`, such as `/lemma survey recent
literature on perovskite solar cell stability`.

Claude writes the brief for Lemma, sends it, and gives you the session link. Runs take
minutes, and long ones take hours. You can keep working with Claude in the meantime: Claude is
told when the run ends and reports what Lemma answered.

## What you can do

**Hand over a task.** Claude starts a session with the goal, what is already known, and any
files you name. Local files are uploaded into the session's workspace in Lemma. Ask Claude to
continue the same session with follow-up questions.

**Use a ready-made workflow.** Lemma has workflows for common jobs, such as surveying the
literature, making a paper interactive, verifying a paper's references, and simulating a device.
Ask Claude which workflows are available, or describe the job and Claude picks the matching
one. Claude asks you for any required input it does not have.

**Plan before running.** In plan mode, Lemma drafts a plan with its tasks and any questions it
has, and nothing runs until you approve the plan. Through Claude you can answer the questions,
edit or remove tasks, run the whole plan or one task at a time, and approve or reject each
finished task. Use plan mode for long or costly studies that you want to shape first.

**Answer Lemma's questions.** When Lemma stops for a decision, such as approval of a step,
Claude puts the question to you and acts only on your answer.

**Bring results back.** Ask Claude to list the files in a session and download the ones you
want. Downloads never overwrite a local file: a name that is already taken gets a number added.

**Open the session in the browser.** Ask Claude to open a session to read every step, view
notebooks, or continue the work yourself in Lemma.

## Settings

Change these with `/plugin configure lemma@axiomatic-ai`.

| Setting | Default | What it does |
| --- | --- | --- |
| Open sessions in the browser | On | Opens each new session in your browser as soon as Claude sends its first message. |
| Default model | Lemma's default | The model a new session uses when you don't name one. Lemma's default is the model Lemma would use in the browser. The other values are Anthropic Pro Fast, Anthropic Pro, Anthropic Normal, Google Pro, Google Normal, Open-weight Pro, and Open-weight Normal. |
| Default machine | Standard | The machine a new session runs on when you don't name one. The values are Standard, Enhanced, High performance, Max, and GPU. Larger machines cost more. The machine cannot change once a session has started. |

Type the model and machine values as shown. Capital letters, spaces, and punctuation don't
matter. If the plugin doesn't recognize a value, Lemma uses its own default, and Claude tells you
the next time it starts a session.

To set them while installing from a terminal, add `--config` to the install command:

```bash
claude plugin install lemma@axiomatic-ai --config "default_machine=High performance"
```

You can also name a model or machine in your request, such as "use a GPU machine for this".
Ask Claude to list the models and machines available to your account and what each machine
costs.

## Your data

- Files you name are uploaded to the Lemma session and stay in that session's workspace, as if
  you had added them in the browser. Claude uploads only the files you name.
- The sign-in is stored in your operating system's keychain under `axiomatic-lemma`. Signing
  out removes it.
- Nothing runs in the background while you are not using Lemma. After Claude starts a run, a
  background process waits for the run to end so it can tell Claude, and then exits.

## Which local files Lemma can reach

Files are sent from, and saved to, the open workspace (the folders Claude Code reports over MCP),
the project (`CLAUDE_PROJECT_DIR`), and any folders listed in `LEMMA_ALLOWED_DIRS` (separated by
`:`). For any other path, Claude Code asks you to allow it first; Claude cannot answer for you.
Hidden files and folders, such as `.env`, `.ssh` or `.aws`, are always refused. Claude cannot
change `LEMMA_ALLOWED_DIRS`; set it in the environment that starts Claude Code.

## What the plugin runs, sends and fetches

- **Runs locally:** the `lemma-mcp` server, which Claude Code starts when the plugin loads and
  keeps for the session, and the `lemma-wake` hook, started after each Lemma tool call that starts
  or waits on a run; it exits at once when no run is going. Both are the Python in
  [`server/`](server/), run with `uv`.
- **Fetches on first start of each plugin version:** `uv` installs the server's runtime
  dependencies from PyPI, pinned by `server/uv.lock`. If no Python 3.12 or newer is installed,
  `uv` first downloads one from its python-build-standalone releases on GitHub.
- **Sends to Lemma:** over HTTPS to `api.axiomatic-ai.com`, the messages, settings and answers
  Claude passes to Lemma's tools, and the files you name in them. Files go to the storage link
  Lemma returns for each upload, and downloads come from the storage link Lemma returns for each
  file, following any redirect that link gives.
- **Signs in with:** `auth.axiomatic-ai.com`, through your browser. The refresh token is kept in
  the OS keychain and sent only to `auth.axiomatic-ai.com`.
- **Opens in your browser:** the sign-in page, each new session on `lemma.axiomatic.ai` unless
  you turned that off, and any session Claude opens with `open_in_browser`.
- **Writes locally:** files you ask Claude to download, into the folders listed under "Which local
  files Lemma can reach", each written first as a `.part` file beside it; the refresh token, in the
  OS keychain; a sign-in lock file in `~/.lemma-mcp`; output Claude saves with `output_file`; and
  the Python environment, in `server/.venv` in the installed plugin and in `uv`'s cache.

Nothing else is sent anywhere.

## Troubleshooting

**The browser didn't open for sign-in.** Claude shows a sign-in link instead. Open it, sign in,
and tell Claude to try again.

**Sign-in fails to complete.** Sign-in receives the browser's redirect on `127.0.0.1`, on the
first free port of 47815, 47816, and 47817. Check that another program is not using all three
and that a firewall is not blocking local connections.

**"Lemma is still working on this conversation."** A Lemma session runs one task at a time.
Wait for the current run to end, or ask Claude to start a new session.

**"This Lemma account has used all of its plan's tokens."** Check your usage and plan in
Lemma's settings in the browser.

**Lemma tools are missing in Claude Code.** Run `/reload-plugins`, and check that `uv --version`
works in the terminal Claude Code was started from.

**The run ended without an answer.** Ask Claude for the session link and open it in the browser
to see what happened.

## Upgrading from `axiomaticai`

Earlier versions of this plugin were named `axiomaticai`. If you have that version installed,
remove it and install `lemma`:

```bash
claude plugin uninstall axiomaticai@axiomatic-ai
```

```bash
claude plugin marketplace update axiomatic-ai
```

```bash
claude plugin install lemma@axiomatic-ai
```

Then restart Claude Code. You stay signed in to Lemma. Your settings are not carried over, so set
them again with `/plugin configure lemma@axiomatic-ai` if you had changed them.

## Update or remove

```bash
claude plugin marketplace update axiomatic-ai
```

```bash
claude plugin update lemma@axiomatic-ai
```

Restart Claude Code after an update. To remove the plugin:

```bash
claude plugin uninstall lemma@axiomatic-ai
```

## Support

Email [developers@axiomatic-ai.com](mailto:developers@axiomatic-ai.com).

To work on the plugin itself, see [CONTRIBUTING.md](../../CONTRIBUTING.md).
