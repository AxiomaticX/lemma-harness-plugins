from pathlib import Path

import httpx
import keyring
import pytest
import respx
from keyring.backend import KeyringBackend

from lemma_mcp.auth import Session
from lemma_mcp.client import LemmaClient
from lemma_mcp.config import Target

TARGET = Target(
    name="test",
    domain="auth.test",
    client_id="client-1",
    audience="https://api.test",
    api_url="https://api.test",
    web_url="https://lemma.test",
)
TOKEN_URL = "https://auth.test/oauth/token"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.secrets.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.secrets[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.secrets[(service, username)]


@pytest.fixture(autouse=True)
def memory_keyring() -> MemoryKeyring:
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False) as router:
        router.route(host="127.0.0.1").pass_through()
        yield router


def token_response(access: str = "at-1", refresh: str = "rt-2", expires_in: int = 3600):
    return httpx.Response(
        200, json={"access_token": access, "refresh_token": refresh, "expires_in": expires_in}
    )


@pytest.fixture
def session(tmp_path: Path) -> Session:
    return Session(TARGET, tmp_path, interactive=False)


@pytest.fixture
def signed_in(session: Session, api) -> Session:
    session.store.set("rt-1")
    api.post(TOKEN_URL).mock(return_value=token_response())
    return session


@pytest.fixture
def client(signed_in: Session) -> LemmaClient:
    return LemmaClient(signed_in)
