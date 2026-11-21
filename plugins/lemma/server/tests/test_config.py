import json
import tomllib
from pathlib import Path

from lemma_mcp.config import TARGET, data_dir, load_settings, save_settings

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


def test_the_manifests_and_the_package_carry_the_same_version():
    project = tomllib.loads((PLUGIN / "server" / "pyproject.toml").read_text())
    for folder in (".claude-plugin", ".antigravity-plugin"):
        manifest = json.loads((PLUGIN / folder / "plugin.json").read_text())
        assert manifest["version"] == project["project"]["version"]


def test_settings_merge_persist_and_ignore_missing_or_corrupt_file(tmp_path: Path):
    assert load_settings(tmp_path) == {}

    save_settings(tmp_path, {"open_browser": False})
    save_settings(tmp_path, {"default_machine": "GPU"})
    assert load_settings(tmp_path) == {"open_browser": False, "default_machine": "GPU"}

    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert load_settings(tmp_path) == {}
