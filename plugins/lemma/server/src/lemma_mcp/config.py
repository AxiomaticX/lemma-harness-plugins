"""Where Lemma lives, how the plugin signs in to it, and where it keeps its sign-in lock."""

import os
import re
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
