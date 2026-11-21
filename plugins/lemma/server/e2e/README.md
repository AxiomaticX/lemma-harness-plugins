# End-to-end checks

These check that the plugin still installs and is wired together. They don't judge Claude's or
Lemma's answers.

```bash
cd plugins/lemma/server
uv run pytest e2e
```

- `test_install.py`: Claude Code adds this checkout as a marketplace, installs the plugin into a
  new project, lists its skill and MCP server, and connects to the server. Both manifests pass
  `claude plugin validate`. Needs the `claude` CLI; no sign-in.
- `test_wiring.py`: the server started as `.mcp.json` starts it lists the expected tools, and the
  wake hook's matcher catches exactly the tools that start or wait on a run.

CI runs both on every pull request (`.github/workflows/tests.yml`).

## Before a release, check by hand

In Claude Code, with the plugin installed from the branch:

1. Sign out of Lemma (`logout` tool), then start a conversation. The browser sign-in opens, and
   the tool goes on once you have signed in.
2. Start a short run and let Claude go idle. When the run ends, Claude wakes on its own and
   reports it.
