"""Where Lemma lives, how the plugin signs in to it, where it keeps its sign-in lock, and
persistent plugin settings."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"


@dataclass(frozen=True)
class Target:
    name: str
    domain: str
    client_id: str
    audience: str
    api_url: str
    web_url: str

    def conversation_url(self, conversation_id: str) -> str:
        return f"{self.web_url}/en/lemma/{conversation_id}"


TARGET = Target(
    name="production",
    domain="auth.axiomatic-ai.com",
    client_id="R1t8IDixr1T4cY9haA3CwuCrwZggu3cC",
    audience="https://api.axiomatic-ai.com",
    api_url="https://api.axiomatic-ai.com",
    web_url="https://lemma.axiomatic.ai",
)


def data_dir() -> Path:
    """Where the sign-in lock lives: one per user, like the keychain token it guards, so every
    process that refreshes that token takes the same lock."""
    chosen = os.environ.get("LEMMA_DATA_DIR")
    return Path(chosen) if chosen else Path.home() / ".lemma-mcp"


def choice_key(label: str) -> str:
    """A setting's value with case, spaces and punctuation removed, for matching what users type."""
    return "".join(re.findall(r"[a-z0-9]+", label.lower()))


def find_choice[V](choices: dict[str, V], typed: str | None) -> V | None:
    """The choice whose label matches what the user typed, or None."""
    wanted = choice_key(typed or "")
    return next((value for label, value in choices.items() if choice_key(label) == wanted), None)


def load_settings(data_dir: Path) -> dict[str, Any]:
    """Read saved plugin settings from ``data_dir/config.json``; empty if missing or invalid."""
    path = data_dir / CONFIG_FILENAME
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def save_settings(data_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge ``updates`` into ``data_dir/config.json`` atomically and return the stored settings."""
    data_dir.mkdir(parents=True, exist_ok=True)
    merged = {**load_settings(data_dir), **updates}
    path = data_dir / CONFIG_FILENAME
    tmp = data_dir / f".{CONFIG_FILENAME}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return merged
