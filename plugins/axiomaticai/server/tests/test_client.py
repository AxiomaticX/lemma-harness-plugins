import httpx
import pytest
from conftest import TOKEN_URL, token_response

from lemma_mcp.client import LemmaClient
from lemma_mcp.errors import BusyError, LemmaError, NotFoundError, UsageLimitError


async def test_calls_carry_the_bearer_token(client: LemmaClient, api):
    route = api.get("https://api.test/ping").mock(return_value=httpx.Response(200))

    await client.request("GET", "/ping")

    assert route.calls.last.request.headers["Authorization"] == "Bearer at-1"


async def test_calls_name_the_plugin_version_and_harness(signed_in, api, monkeypatch):
    monkeypatch.setenv("LEMMA_HARNESS", "codex")
    route = api.get("https://api.test/ping").mock(return_value=httpx.Response(200))

    await LemmaClient(signed_in).request("GET", "/ping")

    assert route.calls.last.request.headers["User-Agent"] == "lemma-mcp/0.6.0 (codex)"


async def test_a_rejected_token_is_refreshed_once_and_the_call_retried(client: LemmaClient, api):
    api.post(TOKEN_URL).mock(
        side_effect=[token_response("at-1", "rt-2"), token_response("at-2", "rt-3")]
    )
    route = api.get("https://api.test/ping").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"ok": True})]
    )

    response = await client.request("GET", "/ping")

    assert response.json() == {"ok": True}
    assert [c.request.headers["Authorization"] for c in route.calls] == [
        "Bearer at-1",
        "Bearer at-2",
    ]


@pytest.mark.parametrize(
    ("status", "error"),
    [(404, NotFoundError), (409, BusyError), (429, UsageLimitError)],
)
async def test_lemma_statuses_become_their_errors(client: LemmaClient, api, status, error):
    api.get("https://api.test/ping").mock(return_value=httpx.Response(status))

    with pytest.raises(error):
        await client.request("GET", "/ping")


async def test_any_other_error_carries_lemmas_detail(client: LemmaClient, api):
    api.get("https://api.test/ping").mock(
        return_value=httpx.Response(500, json={"detail": "The message could not be started."})
    )

    with pytest.raises(LemmaError, match="could not be started"):
        await client.request("GET", "/ping")


@pytest.mark.parametrize("path", ["/files/../users/me", "/files/a?b", "/files/a%2F", "/a//b", "x"])
async def test_a_path_that_could_escape_its_endpoint_is_never_sent(client: LemmaClient, api, path):
    with pytest.raises(LemmaError, match="Refusing"):
        await client.request("GET", path)
    assert not api.calls
