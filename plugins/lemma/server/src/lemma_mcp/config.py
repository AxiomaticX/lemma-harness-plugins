"""Where Lemma lives and how the plugin signs in to it."""

import re
from dataclasses import dataclass


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


def choice_key(label: str) -> str:
    """A setting's value with case, spaces and punctuation removed, for matching what users type."""
    return "".join(re.findall(r"[a-z0-9]+", label.lower()))


def find_choice[V](choices: dict[str, V], typed: str | None) -> V | None:
    """The choice whose label matches what the user typed, or None."""
    wanted = choice_key(typed or "")
    return next((value for label, value in choices.items() if choice_key(label) == wanted), None)


def target(name: str | None) -> Target:
    """The named environment, production when unset."""
    found = find_choice(TARGETS, name or "production")
    if found is None:
        raise ValueError(
            f"The Lemma environment setting is {name!r}, which is not production, staging, or dev."
        )
    return found
