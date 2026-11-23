"""The Lemma API, as the signed-in user."""

import os
import re
from contextlib import asynccontextmanager
from importlib.metadata import version
from typing import Any

import httpx

from ..auth import Session
from ..errors import (
    BusyError,
    LemmaError,
    NotFoundError,
    NotLoggedInError,
    ServerError,
    UsageLimitError,
)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
SAFE_SEGMENT = re.compile(r"[A-Za-z0-9_-]+")


class LemmaClient:
    """Bearer-authenticated calls with one refresh-and-retry on 401."""

    def __init__(self, session: Session, http: httpx.AsyncClient | None = None) -> None:
        self.session = session
        self.target = session.target
        self._http = http or httpx.AsyncClient(
            base_url=self.target.api_url, timeout=TIMEOUT, headers={"User-Agent": user_agent()}
        )

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        check_path(path)
        response = await self._send(method, path, await self.session.access_token(), **kwargs)
        if response.status_code == 401:
            response = await self._send(method, path, await self.session.refresh(), **kwargs)
        raise_for_status(response)
        return response

    @asynccontextmanager
    async def stream(self, method: str, path: str, **kwargs: Any):
        check_path(path)
        token = await self.session.access_token()
        async with self._http.stream(method, path, headers=_bearer(token), **kwargs) as response:
            if response.status_code != 401:
                await _raise_streamed(response)
                yield response
                return
        token = await self.session.refresh()
        async with self._http.stream(method, path, headers=_bearer(token), **kwargs) as response:
            await _raise_streamed(response)
            yield response

    async def _send(self, method: str, path: str, token: str, **kwargs: Any) -> httpx.Response:
        return await self._http.request(method, path, headers=_bearer(token), **kwargs)


def user_agent() -> str:
    """Names the plugin version and the harness running it, so Lemma can tell them apart."""
    harness = os.environ.get("LEMMA_HARNESS", "").strip().lower() or "claude-code"
    return f"lemma-mcp/{version('lemma-mcp')} ({harness})"


def check_path(path: str) -> None:
    """Refuse API paths whose segments could escape the endpoint they were built for."""
    segments = path.removesuffix("/")[1:].split("/")
    if not path.startswith("/") or not all(map(SAFE_SEGMENT.fullmatch, segments)):
        raise LemmaError(f"Refusing to call Lemma at {path!r}: ids hold only A-Z, 0-9, - and _.")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _raise_streamed(response: httpx.Response) -> None:
    if response.is_error:
        await response.aread()
        raise_for_status(response)


def raise_for_status(response: httpx.Response) -> None:
    """Lemma's error responses as the errors the tools report."""
    if not response.is_error:
        return
    match response.status_code:
        case 401:
            raise NotLoggedInError("Lemma did not accept the sign-in. Call the login tool.")
        case 404:
            raise NotFoundError(
                _server_detail(response) or "Lemma has no such conversation, run or file."
            )
        case 409:
            refused = _server_detail(response)
            if refused and "in progress" not in refused:
                raise LemmaError(f"Lemma refused this: {refused}")
            raise BusyError()
        case 429:
            raise UsageLimitError()
    found = _server_detail(response) or f"HTTP {response.status_code}"
    if response.is_server_error:
        raise ServerError(f"Lemma returned an error: {found}")
    raise LemmaError(f"Lemma returned an error: {found}")


def _server_detail(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    found = body.get("detail") if isinstance(body, dict) else None
    if isinstance(found, list):
        found = "; ".join(_field_error(item) for item in found if isinstance(item, dict)) or None
    return found if isinstance(found, str) else None


def _field_error(item: dict) -> str:
    """One of FastAPI's validation errors, as `field: message`."""
    where = ".".join(str(part) for part in (item.get("loc") or [])[1:])
    return f"{where}: {item.get('msg')}" if where else str(item.get("msg"))
