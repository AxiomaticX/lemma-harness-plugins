import json
from importlib.metadata import version
from pathlib import Path

from lemma_mcp.config import TARGET, data_dir

MANIFEST = Path(__file__).parents[2] / ".claude-plugin" / "plugin.json"


def test_the_plugin_talks_to_production_lemma():
    assert TARGET.api_url == "https://api.axiomatic-ai.com"
    assert TARGET.conversation_url("c1") == "https://lemma.axiomatic.ai/en/lemma/c1"


def test_the_server_and_the_hook_share_one_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("LEMMA_DATA_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin"))
    assert data_dir() == tmp_path / "plugin"

    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path / "chosen"))
    assert data_dir() == tmp_path / "chosen"

    monkeypatch.delenv("LEMMA_DATA_DIR")
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA")
    assert data_dir() == Path.home() / ".lemma-mcp"


def test_the_manifest_and_the_package_carry_the_same_version():
    assert json.loads(MANIFEST.read_text())["version"] == version("lemma-mcp")
