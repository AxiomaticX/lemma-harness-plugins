"""Sign-in to Lemma: browser auth-code with PKCE on a loopback callback, refresh in-process."""

import asyncio
import base64
import contextlib
import hashlib
import html
import secrets
import time
import webbrowser
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import keyring
from filelock import AsyncFileLock

from .config import Target
from .errors import LemmaError, NotLoggedInError

KEYRING_SERVICE = "axiomatic-lemma"
CALLBACK_PORTS = (47815, 47816, 47817)
SCOPES = "openid offline_access"
REFRESH_MARGIN_SECONDS = 60
LOGIN_TIMEOUT_SECONDS = 300
LOCK_TIMEOUT_SECONDS = 30

_PAGE = (
    "<!doctype html><meta charset=utf-8><title>Lemma</title>"
    "<body style='font-family:sans-serif;margin:4rem'><h1>{heading}</h1><p>{body}</p>"
)


def pkce_pair() -> tuple[str, str]:
    """A code verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class CallbackListener:
    """Accepts the one redirect the browser makes back to 127.0.0.1 after sign-in."""

    def __init__(self, state: str, ports: tuple[int, ...] = CALLBACK_PORTS) -> None:
        self._state = state
        self._ports = ports
        self._server: asyncio.Server | None = None
        self._code: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self.port: int | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    async def start(self) -> None:
        for port in self._ports:
            try:
                self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
            except OSError:
                continue
            self.port = port
            return
        ports = ", ".join(str(p) for p in self._ports)
        raise LemmaError(f"Lemma sign-in needs one of ports {ports} free on this machine.")

    async def code(self, timeout: float) -> str:
        try:
            return await asyncio.wait_for(asyncio.shield(self._code), timeout)
        except TimeoutError:
            raise NotLoggedInError("Lemma sign-in was not completed in the browser.") from None

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await reader.readline()).decode("latin-1")
            while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass
            parts = request_line.split(" ")
            target = urlsplit(parts[1]) if len(parts) > 1 else None
            if target is None or target.path != "/callback":
                await self._respond(writer, 404, "Not found", "")
                return
            query = {k: v[0] for k, v in parse_qs(target.query).items()}
            if query.get("state") != self._state:
                await self._respond(writer, 400, "Sign-in failed", "The response did not match.")
                return
            if "error" in query:
                detail = query.get("error_description") or query["error"]
                self._settle(error=NotLoggedInError(f"Lemma sign-in failed: {detail}"))
                await self._respond(writer, 400, "Sign-in failed", detail)
                return
            if "code" not in query:
                await self._respond(writer, 400, "Sign-in failed", "No code was returned.")
                return
            self._settle(code=query["code"])
            await self._respond(
                writer, 200, "Signed in to Lemma", "You can close this tab and go back."
            )
        finally:
            writer.close()

    def _settle(self, *, code: str | None = None, error: Exception | None = None) -> None:
        if self._code.done():
            return
        if error is not None:
            self._code.set_exception(error)
        else:
            self._code.set_result(code)

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, status: int, heading: str, body: str) -> None:
        page = _PAGE.format(heading=html.escape(heading), body=html.escape(body)).encode()
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found"}[status]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(page)}\r\nConnection: close\r\n\r\n".encode()
            + page
        )
        await writer.drain()


class TokenStore:
    """The refresh token in the OS keychain, one per environment."""

    def __init__(self, target: Target, data_dir: Path) -> None:
        self._account = target.name
        data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = AsyncFileLock(
            data_dir / f"auth-{target.name}.lock", timeout=LOCK_TIMEOUT_SECONDS
        )

    def get(self) -> str | None:
        return keyring.get_password(KEYRING_SERVICE, self._account)

    def set(self, refresh_token: str) -> None:
        keyring.set_password(KEYRING_SERVICE, self._account, refresh_token)

    def clear(self) -> None:
        if self.get() is not None:
            keyring.delete_password(KEYRING_SERVICE, self._account)


@dataclass
class _AccessToken:
    value: str
    expires_at: float

    def fresh(self) -> bool:
        return time.monotonic() < self.expires_at - REFRESH_MARGIN_SECONDS


class Session:
    """Hands out a current access token, signing in or refreshing as needed."""

    def __init__(
        self,
        target: Target,
        data_dir: Path,
        *,
        interactive: bool = True,
        open_browser: Callable[[str], bool] = webbrowser.open,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.target = target
        self.store = TokenStore(target, data_dir)
        self._interactive = interactive
        self._open_browser = open_browser
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient(timeout=30)
        self._token: _AccessToken | None = None
        self._mutex = asyncio.Lock()
        self._pending_login: asyncio.Task[None] | None = None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def access_token(self) -> str:
        if self._token is not None and self._token.fresh():
            return self._token.value
        return await self.refresh()

    async def refresh(self) -> str:
        """A new access token from the stored refresh token, signing in first if there is none."""
        self._require_client()
        # The wake-up hook rotates the same token, so read it only while holding the file lock.
        async with self._mutex, self.store.lock:
            refresh_token = self.store.get()
            if refresh_token is not None:
                response = await self._http.post(
                    self._token_url,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.target.client_id,
                        "refresh_token": refresh_token,
                    },
                )
                if response.status_code in (400, 401, 403):
                    self.store.clear()
                else:
                    self._accept(response)
                    return self._token.value
        if not self._interactive:
            raise NotLoggedInError("Not signed in to Lemma. Call the login tool.")
        await self.login()
        return self._token.value

    async def login(self) -> None:
        """Sign in through the browser. Without one, raises with the URL and keeps listening."""
        self._require_client()
        if self._pending_login is None or self._pending_login.done():
            url, complete = await self._begin_login()
            self._pending_login = asyncio.create_task(complete)
            if not self._open_browser(url):
                raise NotLoggedInError(
                    f"Sign in to Lemma by opening this link in a browser: {url} "
                    "Then call the tool again."
                )
        await self._pending_login

    async def logout(self) -> None:
        refresh_token = self.store.get()
        self._token = None
        self.store.clear()
        if refresh_token is not None and self.target.client_id:
            with contextlib.suppress(httpx.HTTPError):
                await self._http.post(
                    f"https://{self.target.domain}/oauth/revoke",
                    json={"client_id": self.target.client_id, "token": refresh_token},
                )

    async def _begin_login(self) -> tuple[str, Coroutine[Any, Any, None]]:
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        listener = CallbackListener(state)
        await listener.start()
        url = f"https://{self.target.domain}/authorize?" + urlencode(
            {
                "response_type": "code",
                "client_id": self.target.client_id,
                "redirect_uri": listener.redirect_uri,
                "scope": SCOPES,
                "audience": self.target.audience,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return url, self._complete_login(listener, verifier)

    async def _complete_login(self, listener: CallbackListener, verifier: str) -> None:
        try:
            code = await listener.code(LOGIN_TIMEOUT_SECONDS)
        finally:
            await listener.close()
        response = await self._http.post(
            self._token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": self.target.client_id,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": listener.redirect_uri,
            },
        )
        if response.is_error:
            raise NotLoggedInError(f"Lemma sign-in failed: {_error_detail(response)}")
        async with self.store.lock:
            self._accept(response)

    def _accept(self, response: httpx.Response) -> None:
        if response.is_error:
            raise LemmaError(f"Lemma sign-in service error: {_error_detail(response)}")
        body = response.json()
        if body.get("refresh_token"):
            self.store.set(body["refresh_token"])
        self._token = _AccessToken(
            value=body["access_token"],
            expires_at=time.monotonic() + float(body.get("expires_in", 3600)),
        )

    def _require_client(self) -> None:
        if not self.target.client_id:
            raise LemmaError("This build of the plugin has no Lemma sign-in configured.")

    @property
    def _token_url(self) -> str:
        return f"https://{self.target.domain}/oauth/token"


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    return body.get("error_description") or body.get("error") or f"HTTP {response.status_code}"
