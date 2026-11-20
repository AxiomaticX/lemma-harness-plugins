"""Where Lemma lives, how the plugin signs in to it, and persistent plugin settings."""

import json
import os
import tempfile
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


TARGETS = {
    "production": Target(
        name="production",
        domain="auth.axiomatic-ai.com",
        client_id="R1t8IDixr1T4cY9haA3CwuCrwZggu3cC",
        audience="https://api.axiomatic-ai.com",
        api_url="https://api.axiomatic-ai.com",
        web_url="https://lemma.axiomatic.ai",
    ),
    "staging": Target(
        name="staging",
        domain="auth.staging.axiomatic-ai.com",
        client_id="6migihYWWtTdPl6WLWyaPpCjJ4XJrFr3",
        audience="https://api.staging.axiomatic-ai.com",
        api_url="https://api.staging.axiomatic-ai.com",
        web_url="https://lemma.staging.axiomatic.ai",
    ),
    "dev": Target(
        name="dev",
        domain="axiomatic-ai-dev.us.auth0.com",
        client_id="KVxATHrcc0iNPgRwTZP9r3e8E4aGRTel",
        audience="https://api.dev.axiomatic-ai.com",
        api_url="https://api.dev.axiomatic-ai.com",
        web_url="https://platform.dev.axiomatic-ai.com",
    ),
}


def target(name: str | None) -> Target:
    """The named environment, production when unset."""
    key = (name or "production").strip().lower()
    if key not in TARGETS:
        raise ValueError(f"Unknown Lemma environment {name!r}; use one of {', '.join(TARGETS)}.")
    return TARGETS[key]


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
    fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=f".{CONFIG_FILENAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(merged, indent=2) + "\n")
        os.replace(tmp, data_dir / CONFIG_FILENAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return merged
