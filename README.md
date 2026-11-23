# Lemma harness plugins

Plugins that connect coding agents to [Lemma](https://lemma.axiomatic.ai), Axiomatic AI's agent
for research and computing in science and engineering.

- [Lemma for Claude Code](plugins/lemma/README.md): install, sign in, settings, and what the
  plugin runs, sends and fetches.
- [Lemma for Google Antigravity](#lemma-for-google-antigravity): the same plugin, installed in
  Antigravity.

## Lemma for Google Antigravity

Requires the Antigravity app or `agy` CLI, and
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) on your `PATH`. Install `lemma`
from GitHub:

```bash
agy plugin install https://github.com/AxiomaticX/lemma-harness-plugins/tree/main/plugins/lemma
```

Sign-in, usage and what the plugin sends work as described for
[Claude Code](plugins/lemma/README.md).

To change settings, ask the agent to configure Lemma, for example "configure Lemma not to open
the browser". That calls the `configure` tool, which applies the change at once and saves it to
`~/.lemma-mcp/config.json`. The settings are `open_browser`, `default_model`, `default_machine`
and `max_tool_output_chars`, with the values listed in the
[settings table](plugins/lemma/README.md#settings). `LEMMA_OPEN_BROWSER`, `LEMMA_DEFAULT_MODEL`,
`LEMMA_DEFAULT_MACHINE` and `LEMMA_MAX_TOOL_OUTPUT_CHARS` in the environment that starts
Antigravity override the saved values.

In Antigravity, `wait_for_result` runs in the background with no time limit and wakes the agent
when the run ends, or after `wake_after_minutes` (60 by default) with outcome `running`. The
agent can't end its turn while a run it started has no wait on it: the plugin's stop hook sends
it back to call `wait_for_result`.

To work on the plugins, see [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the
[MIT License](LICENSE).
