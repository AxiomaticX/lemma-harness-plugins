# Lemma for Google Antigravity

[Lemma](https://lemma.axiomatic.ai) is [Axiomatic AI](https://axiomatic.ai)'s agent for research
and computing in science and engineering. It works on its own machine, with its own tools, and
keeps a record of every step in a session you can open in the browser.

This plugin lets Antigravity hand work to Lemma. From Antigravity you can start a Lemma session,
send it local files, wait for the run to finish, read Lemma's answer, and download the files it
produced. Any session can be opened in the browser to read the full record or to continue the
work there.

## Before you install

- **A Lemma account.** Sign up at [lemma.axiomatic.ai](https://lemma.axiomatic.ai).
- **Usage is charged to that account.** Every message Antigravity sends to Lemma starts a run,
  and each run costs the same as a message typed in the browser. Antigravity tells you what it
  asked Lemma to do and gives you a link to the session.
- **Google Antigravity**, and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) on
  your `PATH`. The plugin runs a small local server with `uv`.

## Install

In the Antigravity app, open **Customizations**, then **Marketplace**, and add **Lemma**.

To install from a terminal instead:

```bash
agy plugin install lemma@antigravity-plugins-official
```

Or install it straight from GitHub:

```bash
agy plugin install https://github.com/AxiomaticX/lemma-harness-plugins/tree/main/plugins/lemma
```

If Lemma's tools don't appear after installing, restart Antigravity.

To update Lemma, run the install command you used again, then restart Antigravity.

## Sign in

The first time Antigravity uses Lemma, your browser opens to the Lemma sign-in page. Sign in with
your usual Lemma account. The plugin keeps the sign-in in your operating system's keychain, so
you stay signed in across restarts. To sign out, ask Antigravity to sign out of Lemma.

## First use

Ask Antigravity in your own words. For example:

- "Ask Lemma to survey recent literature on perovskite solar cell stability."
- "Send `data/sweep.csv` to Lemma and have it fit the resonance peaks. Download the plots when
  it is done."
- "Have Lemma check the references in `paper.pdf`."
- "Ask Lemma to plan a simulation of this waveguide, but don't run anything until I approve the
  plan."

To make sure Antigravity uses Lemma, start the request with `/lemma`, such as `/lemma survey
recent literature on perovskite solar cell stability`.

Antigravity writes the brief for Lemma, sends it, and gives you the session link. Runs take
minutes, and long ones take hours. You can keep working with Antigravity in the meantime: it waits
for the run in the background and reports what Lemma answered when the run ends. If a run is
still going after an hour, Antigravity starts waiting again.

## What you can do

**Hand over a task.** Antigravity starts a session with the goal, what is already known, and any
files you name. Local files are uploaded into the session's workspace in Lemma. Ask Antigravity
to continue the same session with follow-up questions.

**Pick up an earlier session.** Ask Antigravity to find one of your Lemma sessions by what it was
about, or to list your recent ones. It can read what was said and continue from there.

**Use a ready-made workflow.** Lemma has workflows for common jobs, such as surveying the
literature, making a paper interactive, verifying a paper's references, and simulating a device.
Ask Antigravity which workflows are available, or describe the job and Antigravity picks the
matching one. Antigravity asks you for any required input it does not have.

**Plan before running.** In plan mode, Lemma drafts a plan with its tasks and any questions it
has, and nothing runs until you approve the plan. Through Antigravity you can answer the
questions, edit or remove tasks, run the whole plan or one task at a time, and approve or reject
each finished task. Use plan mode for long or costly studies that you want to shape first.

**Answer Lemma's questions.** When Lemma stops for a decision, such as approval of a step,
Antigravity puts the question to you and acts only on your answer.

**Bring results back.** Ask Antigravity to list the files in a session and download the ones you
want. Downloads never overwrite a local file: a name that is already taken gets a number added.

**Open the session in the browser.** Ask Antigravity to open a session to read every step, view
notebooks, or continue the work yourself in Lemma.

## Settings

Ask Antigravity to change a setting in your own words, such as "set Lemma to not open the
browser" or "use the GPU machine for Lemma by default". The change applies at once and is kept
when the plugin updates. Ask Antigravity to show Lemma's settings to see the current values.

| Setting | Default | What it does |
| --- | --- | --- |
| Open sessions in the browser | On | Opens each new session in your browser as soon as Antigravity sends its first message. |
| Default model | Lemma's default | The model a new session uses when you don't name one. Lemma's default is the model Lemma would use in the browser. The other values are Anthropic Pro Fast, Anthropic Pro, Anthropic Normal, Google Pro, Google Normal, Open-weight Pro, and Open-weight Normal. |
| Default machine | Lemma's default | The machine a new session runs on when you don't name one. Lemma's default is the machine Lemma would use in the browser. The other values are Standard, Enhanced, High performance, Max, and GPU. Larger machines cost more. The machine cannot change once a session has started. |
| Tool output cap | 40000 | The most characters the tools that read sessions, plans and results return to Antigravity. A longer result is cut, and Antigravity can save the whole of it to a file instead. |

To fix a setting for every start instead, set `LEMMA_OPEN_BROWSER`, `LEMMA_DEFAULT_MODEL`,
`LEMMA_DEFAULT_MACHINE` or `LEMMA_MAX_TOOL_OUTPUT_CHARS` in the environment that starts
Antigravity, then restart it. A variable that is set wins over the saved setting each time
Antigravity starts.

You can also name a model or machine in your request, such as "use a GPU machine for this".
Ask Antigravity to list the models and machines available to your account and what each machine
costs.

## Your data

- Files you name are uploaded to the Lemma session and stay in that session's workspace, as if
  you had added them in the browser. Antigravity uploads only the files you name.
- The sign-in is stored in your operating system's keychain under `axiomatic-lemma`. Signing
  out removes it.
- Your settings are saved in `~/.lemma-mcp/config.json`, readable only by you.

## Which local files Lemma can reach

Files are sent from, and saved to, the folders open in Antigravity and any folders listed in
`LEMMA_ALLOWED_DIRS` (separated by `:`). If no folder is open, a `workspace` folder in the
plugin's data folder is used instead. For any other path, Antigravity asks you to allow it first,
or the plugin refuses it; the agent cannot allow it for you. Hidden files and folders, such as
`.env`, `.ssh` or `.aws`, are always refused. Antigravity cannot change `LEMMA_ALLOWED_DIRS`; set
it in the environment that starts Antigravity.

## What the plugin runs, sends and fetches

- **Runs locally:** the `lemma-mcp` server, which Antigravity starts when the plugin loads, and
  the `lemma-unwaited` hook, which runs when Antigravity's agent finishes a turn and sends it back
  to wait on any Lemma run it started but isn't waiting on yet. Both are the Python in the
  plugin's `server/` folder, run with `uv` by `scripts/lemma` (`scripts/lemma.cmd` on Windows).
- **Fetches on first start of each plugin version:** `uv` installs the server's runtime
  dependencies from PyPI (`pypi.org`, `files.pythonhosted.org`), pinned by `server/uv.lock`. If
  no Python 3.12 or newer is installed, `uv` first downloads a python-build-standalone release from
  `releases.astral.sh`, or from GitHub with older versions of `uv`.
- **Sends to Lemma:** over HTTPS to `api.axiomatic-ai.com`, the messages, settings and answers
  Antigravity passes to Lemma's tools, and the files you name in them. Files go to the storage
  link Lemma returns for each upload, and downloads come from the storage link Lemma returns for
  each file, following any redirect that link gives.
- **Signs in with:** `auth.axiomatic-ai.com`, through your browser. The refresh token is kept in
  the OS keychain and sent only to `auth.axiomatic-ai.com`.
- **Opens in your browser:** the sign-in page, each new session on `lemma.axiomatic.ai` unless
  you turned that off, and any session Antigravity opens with `open_in_browser`.
- **Writes locally:** files you ask Antigravity to download, into the folders listed under "Which
  local files Lemma can reach", each written first as a `.part` file beside it; the refresh
  token, in the OS keychain; your settings and a sign-in lock file in `~/.lemma-mcp`; a note of
  each run Antigravity started and is not yet waiting on, in the plugin's data folder; output
  Antigravity saves with `output_file`; and the Python environment, in `server/.venv` in the
  installed plugin and in `uv`'s cache.

Nothing else is sent anywhere.

## Troubleshooting

**The browser didn't open for sign-in.** Antigravity shows a sign-in link instead. Open it, sign
in, and tell Antigravity to try again.

**Sign-in fails to complete.** Sign-in receives the browser's redirect on `127.0.0.1`, on the
first free port of 47815, 47816, and 47817. Check that another program is not using all three
and that a firewall is not blocking local connections.

**"Lemma is still working on this session."** A Lemma session runs one task at a time.
Wait for the current run to end, or ask Antigravity to start a new session.

**"This Lemma account has used all of its plan's tokens."** Check your usage and plan in
Lemma's settings in the browser.

**Lemma tools are missing in Antigravity.** Restart Antigravity, and check that `uv --version`
works in a terminal.

**The run ended without an answer.** Ask Antigravity for the session link and open it in the
browser to see what happened.

## Remove

In the Antigravity app, open **Customizations**, then **Installed**, and choose **Uninstall** from
the **⋮** menu beside Lemma. From a terminal:

```bash
agy plugin uninstall lemma
```

You stay signed in to Lemma, and your settings in `~/.lemma-mcp/config.json` are kept.
Uninstalling deletes the plugin's data folder, including the `workspace` folder used when no
folder is open.

## Support

Email [developers@axiomatic-ai.com](mailto:developers@axiomatic-ai.com).
