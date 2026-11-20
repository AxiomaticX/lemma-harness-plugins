import asyncio
import base64
import hashlib
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import TARGET, TOKEN_URL, token_response

from lemma_mcp.auth import CallbackListener, Session, pkce_pair
from lemma_mcp.config import Target
from lemma_mcp.errors import LemmaError, NotLoggedInError


def _free_ports(n: int) -> tuple[int, ...]:
    sockets = [socket.socket() for _ in range(n)]
    for s in sockets:
        s.bind(("127.0.0.1", 0))
    ports = tuple(s.getsockname()[1] for s in sockets)
    for s in sockets:
        s.close()
    return ports


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_the_challenge_is_the_s256_of_the_verifier():
    verifier, challenge = pkce_pair()

    assert 43 <= len(verifier) <= 128
    digest = hashlib.sha256(verifier.encode()).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


async def test_the_callback_hands_over_the_code_for_the_matching_state():
    listener = CallbackListener("state-1", ports=_free_ports(1))
    await listener.start()
    async with httpx.AsyncClient() as browser:
        wrong = await browser.get(listener.redirect_uri, params={"code": "c", "state": "other"})
        right = await browser.get(listener.redirect_uri, params={"code": "c", "state": "state-1"})

    assert wrong.status_code == 400
    assert right.status_code == 200
    assert await listener.code(timeout=1) == "c"
    await listener.close()


async def test_a_denied_sign_in_is_reported():
    listener = CallbackListener("s", ports=_free_ports(1))
    await listener.start()
    async with httpx.AsyncClient() as browser:
        await browser.get(
            listener.redirect_uri,
            params={"state": "s", "error": "access_denied", "error_description": "No."},
        )

    with pytest.raises(NotLoggedInError, match="No."):
        await listener.code(timeout=1)
    await listener.close()


async def test_the_callback_page_escapes_what_the_redirect_carries():
    listener = CallbackListener("s", ports=_free_ports(1))
    await listener.start()
    async with httpx.AsyncClient() as browser:
        page = await browser.get(
            listener.redirect_uri,
            params={"state": "s", "error": "x", "error_description": "<script>x()</script>"},
        )

    assert "<script>" not in page.text
    assert "&lt;script&gt;x()&lt;/script&gt;" in page.text
    with pytest.raises(NotLoggedInError):
        await listener.code(timeout=1)
    await listener.close()


async def test_the_listener_takes_the_next_port_when_one_is_busy():
    taken, free = _free_ports(2)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", taken))
    blocker.listen()
    listener = CallbackListener("s", ports=(taken, free))
    try:
        await listener.start()
        assert listener.port == free
    finally:
        blocker.close()
        await listener.close()


async def test_a_refresh_stores_the_rotated_token(session: Session, api):
    session.store.set("rt-1")
    route = api.post(TOKEN_URL).mock(return_value=token_response(refresh="rt-2"))

    assert await session.access_token() == "at-1"
    assert _form(route.calls.last.request)["refresh_token"] == "rt-1"
    assert session.store.get() == "rt-2"


async def test_a_fresh_access_token_is_reused(signed_in: Session, api):
    await signed_in.access_token()
    await signed_in.access_token()

    assert api.calls.call_count == 1


async def test_a_second_process_refreshes_with_the_token_the_first_one_rotated_in(
    tmp_path: Path, api
):
    first = Session(TARGET, tmp_path, interactive=False)
    second = Session(TARGET, tmp_path, interactive=False)
    first.store.set("rt-1")
    route = api.post(TOKEN_URL).mock(
        side_effect=[token_response(refresh="rt-2"), token_response(refresh="rt-3")]
    )

    await first.access_token()
    await second.access_token()

    sent = [_form(call.request)["refresh_token"] for call in route.calls]
    assert sent == ["rt-1", "rt-2"]
    assert first.store.get() == "rt-3"


async def test_a_refresh_cancelled_while_waiting_for_the_lock_leaves_it_free(tmp_path: Path, api):
    holder = Session(TARGET, tmp_path, interactive=False)
    waiter = Session(TARGET, tmp_path, interactive=False)
    holder.store.set("rt-1")
    api.post(TOKEN_URL).mock(return_value=token_response())

    async with holder.store.lock:
        blocked = asyncio.create_task(waiter.refresh())
        await asyncio.sleep(0.2)
        blocked.cancel()
        with pytest.raises(asyncio.CancelledError):
            await blocked

    assert await asyncio.wait_for(waiter.refresh(), timeout=5) == "at-1"


async def test_a_rejected_refresh_token_signs_out(session: Session, api):
    session.store.set("rt-1")
    api.post(TOKEN_URL).mock(return_value=httpx.Response(403, json={"error": "invalid_grant"}))

    with pytest.raises(NotLoggedInError):
        await session.access_token()
    assert session.store.get() is None


async def test_without_a_client_id_sign_in_says_it_is_not_configured(tmp_path: Path):
    unconfigured = Target(**{**TARGET.__dict__, "client_id": ""})

    with pytest.raises(LemmaError, match="has no Lemma sign-in configured"):
        await Session(unconfigured, tmp_path).access_token()


async def _complete_in_browser(url: str, code: str = "code-1") -> None:
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    async with httpx.AsyncClient() as browser:
        await browser.get(query["redirect_uri"], params={"code": code, "state": query["state"]})


async def test_sign_in_exchanges_the_code_with_the_verifier(tmp_path: Path, api):
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        asyncio.get_running_loop().create_task(_complete_in_browser(url))
        return True

    session = Session(TARGET, tmp_path, open_browser=open_browser)
    route = api.post(TOKEN_URL).mock(return_value=token_response(refresh="rt-new"))

    assert await session.access_token() == "at-1"

    query = {k: v[0] for k, v in parse_qs(urlsplit(opened[0]).query).items()}
    assert query["scope"] == "openid offline_access"
    assert query["audience"] == "https://api.test"
    assert query["code_challenge_method"] == "S256"
    sent = _form(route.calls.last.request)
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "code-1"
    digest = hashlib.sha256(sent["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == query["code_challenge"]
    assert session.store.get() == "rt-new"


async def test_without_a_browser_the_link_is_returned_and_sign_in_completes_later(
    tmp_path: Path, api
):
    session = Session(TARGET, tmp_path, open_browser=lambda _url: False)
    api.post(TOKEN_URL).mock(return_value=token_response())

    with pytest.raises(NotLoggedInError, match="https://auth.test/authorize") as raised:
        await session.access_token()
    url = str(raised.value).split("browser: ")[1].split(" ")[0]
    await _complete_in_browser(url)

    assert await session.access_token() == "at-1"


async def test_logout_forgets_the_refresh_token_and_revokes_it(signed_in: Session, api):
    revoke = api.post("https://auth.test/oauth/revoke").mock(return_value=httpx.Response(200))

    await signed_in.logout()

    assert signed_in.store.get() is None
    assert revoke.called
