"""The plugin as Claude Code sees it: its manifests, and its server and hook started their way."""

import json
import os
import re
import subprocess
from pathlib import Path

from mcp import StdioServerParameters

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PLUGIN_ROOT.parents[1]

PLUGIN = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
SERVERS = json.loads((PLUGIN_ROOT / ".mcp.json").read_text())["mcpServers"]
HOOKS = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())["hooks"]
(WAKE_HOOK,) = HOOKS["PostToolUse"]

PLUGIN_NAME = PLUGIN["name"]
(SERVER_NAME,) = SERVERS


def tool_name(tool: str) -> str:
    """The name Claude Code gives one of the plugin's MCP tools."""
    plugin, server = (re.sub(r"[^a-zA-Z0-9_-]", "_", n) for n in (PLUGIN_NAME, SERVER_NAME))
    return f"mcp__plugin_{plugin}_{server}__{tool}"


def _expand(value: str, data_dir: Path) -> str:
    """A .mcp.json value with Claude Code's variables filled in, settings at their defaults."""

    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "CLAUDE_PLUGIN_ROOT":
            return str(PLUGIN_ROOT)
        if name == "CLAUDE_PLUGIN_DATA":
            return str(data_dir)
        if name.startswith("user_config."):
            default = PLUGIN["userConfig"][name.removeprefix("user_config.")]["default"]
            return json.dumps(default) if isinstance(default, bool) else str(default)
        raise AssertionError(f"Unknown variable ${{{name}}} in .mcp.json")

    return re.sub(r"\$\{([^}]+)\}", one, value)


def server_params(data_dir: Path, **env: str) -> StdioServerParameters:
    """The plugin's MCP server, started exactly as .mcp.json says."""
    spec = SERVERS[SERVER_NAME]
    return StdioServerParameters(
        command=spec["command"],
        args=[_expand(a, data_dir) for a in spec["args"]],
        env={k: _expand(v, data_dir) for k, v in spec.get("env", {}).items()} | env,
    )


def run_wake_hook(event: dict, data_dir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """The PostToolUse command from hooks.json, run as Claude Code runs it, fed one event."""
    (hook,) = WAKE_HOOK["hooks"]
    return subprocess.run(
        hook["command"],
        shell=True,
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ
        | {"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT), "CLAUDE_PLUGIN_DATA": str(data_dir)}
        | env,
    )
