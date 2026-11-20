"""Where Lemma lives, how the plugin signs in to it, and where it keeps its sign-in lock."""

import os
from dataclasses import dataclass
from pathlib import Path


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
    """The one directory the server and the wake hook share, so they hold the same sign-in lock."""
    chosen = os.environ.get("LEMMA_DATA_DIR") or os.environ.get("CLAUDE_PLUGIN_DATA")
    return Path(chosen) if chosen else Path.home() / ".lemma-mcp"
