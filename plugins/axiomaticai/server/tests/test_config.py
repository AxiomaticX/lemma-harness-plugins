from pathlib import Path

import pytest

from lemma_mcp.config import load_settings, save_settings, target


@pytest.mark.parametrize(
    ("name", "api_url"),
    [
        (None, "https://api.axiomatic-ai.com"),
        ("", "https://api.axiomatic-ai.com"),
        ("production", "https://api.axiomatic-ai.com"),
        (" Staging ", "https://api.staging.axiomatic-ai.com"),
        ("dev", "https://api.dev.axiomatic-ai.com"),
    ],
)
def test_the_environment_named_or_production(name, api_url):
    assert target(name).api_url == api_url


def test_an_unknown_environment_is_refused():
    with pytest.raises(ValueError, match="production, staging, dev"):
        target("local")


def test_settings_merge_persist_and_ignore_missing_or_corrupt_file(tmp_path: Path):
    assert load_settings(tmp_path) == {}

    save_settings(tmp_path, {"environment": "staging", "open_browser": False})
    save_settings(tmp_path, {"default_machine": "GPU"})
    assert load_settings(tmp_path) == {
        "environment": "staging",
        "open_browser": False,
        "default_machine": "GPU",
    }

    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    assert load_settings(tmp_path) == {}
