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

Antigravity has no hook to wake the agent when a run ends, so `wait_for_result` runs in the
background with no time limit and wakes the agent when the run ends, or after
`wake_after_minutes` (60 by default) with outcome `running`.

To work on the plugins, see [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the
[MIT License](LICENSE).
