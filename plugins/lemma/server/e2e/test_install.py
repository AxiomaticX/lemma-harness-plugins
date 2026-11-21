"""Claude Code accepts the marketplace and the plugin, and the plugin's server connects."""

import os
import re
import subprocess
from pathlib import Path

import pytest
from conftest import PLUGIN_NAME, PLUGIN_ROOT, REPO_ROOT, SERVER_NAME

MARKETPLACE = "axiomatic-ai"
INSTALLED = f"{PLUGIN_NAME}@{MARKETPLACE}"


def claude(*args: str, cwd: Path, config_dir: Path) -> str:
    """Run the claude CLI against its own config directory, failing the test on a non-zero exit."""
    env = os.environ | {"CLAUDE_CONFIG_DIR": str(config_dir), "MCP_TIMEOUT": "120000"}
    done = subprocess.run(
        ["claude", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300
    )
    output = done.stdout + done.stderr
    assert done.returncode == 0, f"claude {' '.join(args)} exited {done.returncode}:\n{output}"
    return output


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> tuple[Path, Path]:
    """A new project with this checkout added as a marketplace and the plugin installed in it."""
    root = tmp_path_factory.mktemp("install")
    project, config = root / "project", root / "config"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    claude("plugin", "marketplace", "add", str(REPO_ROOT), "--scope", "project",
           cwd=project, config_dir=config)  # fmt: skip
    claude("plugin", "install", INSTALLED, "--scope", "project", cwd=project, config_dir=config)
    return project, config


@pytest.mark.parametrize("path", [PLUGIN_ROOT, REPO_ROOT], ids=["plugin", "marketplace"])
def test_the_manifest_passes_validation(path, tmp_path):
    # Not --strict: it also fails on the directory-listing fields Claude Code ignores.
    claude("plugin", "validate", str(path), cwd=REPO_ROOT, config_dir=tmp_path)


def test_the_installed_plugin_has_its_skill_and_mcp_server(project):
    details = claude("plugin", "details", INSTALLED, cwd=project[0], config_dir=project[1])

    def listed(kind: str) -> set[str]:
        found = re.search(rf"^\s*{kind} \(\d+\)\s+(.+)$", details, re.MULTILINE)
        assert found, f"No {kind} line in:\n{details}"
        names = found.group(1).split("  ")[0]  # drop a note such as "(… not counted)"
        return {name.strip() for name in names.split(",")}

    skills = {p.name for p in (PLUGIN_ROOT / "skills").iterdir() if (p / "SKILL.md").exists()}
    assert listed("Skills") == skills
    assert listed("MCP servers") == {SERVER_NAME}


def test_the_mcp_server_connects(project):
    listing = claude("mcp", "list", cwd=project[0], config_dir=project[1])

    prefix = f"plugin:{PLUGIN_NAME}:{SERVER_NAME}:"
    lines = [line for line in listing.splitlines() if line.startswith(prefix)]
    assert len(lines) == 1, listing
    assert lines[0].endswith("Connected"), listing
