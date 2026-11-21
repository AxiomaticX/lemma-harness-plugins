# Lemma harness plugins

Plugins that connect coding agents to [Lemma](https://lemma.axiomatic.ai), Axiomatic AI's agent
for research and computing in science and engineering.

- [Lemma for Claude Code](plugins/lemma/README.md): install, sign in, settings, and what the
  plugin runs, sends and fetches.
- [Lemma for OpenAI Codex](#lemma-for-openai-codex): the same plugin, installed in Codex.

## Lemma for OpenAI Codex

Requires the Codex CLI or app, and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
on your `PATH`. Add this repository as a marketplace and install `lemma`:

```bash
codex plugin marketplace add AxiomaticX/lemma-harness-plugins
```

```bash
codex plugin add lemma@axiomatic-ai
```

Or open `/plugins` in Codex, choose the **Axiomatic AI** marketplace, and install **Lemma**.

Sign-in, usage and what the plugin sends work as described for
[Claude Code](plugins/lemma/README.md). Settings come from the environment that starts Codex:
`LEMMA_OPEN_BROWSER`, `LEMMA_DEFAULT_MODEL`, `LEMMA_DEFAULT_MACHINE`,
`LEMMA_MAX_TOOL_OUTPUT_CHARS` and `LEMMA_ALLOWED_DIRS`, with the values listed in the
[settings table](plugins/lemma/README.md#settings).

Codex has no hook to wake the agent when a run ends, so `wait_for_result` waits up to 240 seconds
per call and returns `running` when the run takes longer, and Codex calls it again. That stays
below Codex's default MCP tool timeout of 300 seconds; keep `tool_timeout_sec` at 300 or more if
you set it.

To work on the plugins, see [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the
[MIT License](LICENSE).
