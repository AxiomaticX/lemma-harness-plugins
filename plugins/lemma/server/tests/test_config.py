import json
import tomllib
from pathlib import Path

from lemma_mcp.config import TARGET, data_dir

PLUGIN = Path(__file__).parents[2]


def test_the_plugin_talks_to_production_lemma():
    assert TARGET.api_url == "https://api.axiomatic-ai.com"
    assert TARGET.conversation_url("c1") == "https://lemma.axiomatic.ai/en/lemma/c1"


def test_the_sign_in_lock_is_one_per_user_whatever_harness_runs(monkeypatch, tmp_path):
    monkeypatch.delenv("LEMMA_DATA_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin"))
    assert data_dir() == Path.home() / ".lemma-mcp"

    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path / "chosen"))
    assert data_dir() == tmp_path / "chosen"


def test_the_manifest_and_the_package_carry_the_same_version():
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    project = tomllib.loads((PLUGIN / "server" / "pyproject.toml").read_text())
    assert manifest["version"] == project["project"]["version"]
