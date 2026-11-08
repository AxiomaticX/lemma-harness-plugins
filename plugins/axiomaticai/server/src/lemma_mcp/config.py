"""Where Lemma lives and how the plugin signs in to it."""

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


def target(name: str | None) -> Target:
    """The named environment, production when unset."""
    key = (name or "production").strip().lower()
    if key not in TARGETS:
        raise ValueError(f"Unknown Lemma environment {name!r}; use one of {', '.join(TARGETS)}.")
    return TARGETS[key]
