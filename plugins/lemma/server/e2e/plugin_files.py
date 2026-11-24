"""The plugin as Claude Code sees it: its manifests, and its server and hook started their way."""

import json
import os
import re
import shutil
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


def clean_copy(dest: Path) -> Path:
    """The plugin from a copy of this checkout without its .venv, so its server and hook build
    the environment a user gets. Copies tracked and new files, leaves out ignored ones."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for name in filter(None, listed.split("\0")):
        if (REPO_ROOT / name).is_file():  # not a file deleted but still in the index
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / name, dest / name)
    return dest / PLUGIN_ROOT.relative_to(REPO_ROOT)


def _expand(value: str, plugin_root: Path, data_dir: Path) -> str:
    """A .mcp.json value with Claude Code's variables filled in, settings at their defaults."""

    def one(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "CLAUDE_PLUGIN_ROOT":
            return str(plugin_root)
        if name == "CLAUDE_PLUGIN_DATA":
            return str(data_dir)
        if name.startswith("user_config."):
            default = PLUGIN["userConfig"][name.removeprefix("user_config.")]["default"]
            return json.dumps(default) if isinstance(default, bool) else str(default)
        raise AssertionError(f"Unknown variable ${{{name}}} in .mcp.json")

    return re.sub(r"\$\{([^}]+)\}", one, value)


def server_params(plugin_root: Path, data_dir: Path, **env: str) -> StdioServerParameters:
    """The plugin's MCP server, started exactly as .mcp.json says."""
    spec = SERVERS[SERVER_NAME]
    return StdioServerParameters(
        command=spec["command"],
        args=[_expand(a, plugin_root, data_dir) for a in spec["args"]],
        env={k: _expand(v, plugin_root, data_dir) for k, v in spec.get("env", {}).items()} | env,
    )


def run_wake_hook(
    event: dict, plugin_root: Path, data_dir: Path
) -> subprocess.CompletedProcess[str]:
    """The PostToolUse command from hooks.json, run as Claude Code runs it, fed one event.

    It sees only PATH and HOME, and a keyring that holds no Lemma token, so it never signs in.
    """
    (hook,) = WAKE_HOOK["hooks"]
    return subprocess.run(
        hook["command"],
        shell=True,
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ["HOME"],
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "LEMMA_DATA_DIR": str(data_dir),
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        },
    )
