"""Starting a run on a conversation, reading how it ended, and waiting for it."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ..errors import LemmaError
from . import LemmaClient

RUNNING = "running"
TERMINAL_TYPES = "RUN_FINISHED,RUN_ERROR"
SEND_READ_TIMEOUT_SECONDS = 75.0
STREAM_READ_TIMEOUT_SECONDS = 90.0
MIN_STREAM_SECONDS = 5.0
POLL_SECONDS = 5.0


@dataclass(frozen=True)
class RunResult:
    outcome: str
    answer: str | None


async def send(
    client: LemmaClient,
    conversation_id: str,
    content: str,
    file_ids: list[str],
    options: dict[str, Any],
) -> str:
    """Start the conversation's next run with one message; returns the run id."""
    response = await client.request(
        "POST",
        f"/conversations/{conversation_id}/messages",
        json={"content": content, "file_ids": file_ids, **options},
        timeout=httpx.Timeout(30.0, read=SEND_READ_TIMEOUT_SECONDS),
    )
    return response.json()["run_id"]


async def result(client: LemmaClient, conversation_id: str, run_id: str) -> RunResult:
    response = await client.request("GET", f"/conversations/{conversation_id}/runs/{run_id}")
    body = response.json()
    return RunResult(outcome=body["outcome"], answer=body.get("answer"))


async def wait(client: LemmaClient, conversation_id: str, run_id: str, timeout: float) -> RunResult:
    """The stored result once the run stops, or after ``timeout``; the stream only wakes it."""
    deadline = time.monotonic() + timeout
    while True:
        current = await result(client, conversation_id, run_id)
        remaining = deadline - time.monotonic()
        if current.outcome != RUNNING or remaining <= 0:
            return current
        started = time.monotonic()
        try:
            async with asyncio.timeout(remaining):
                await _follow_stream(client, conversation_id)
        except TimeoutError:
            continue
        except (httpx.TransportError, LemmaError):
            pass
        if time.monotonic() - started < MIN_STREAM_SECONDS:
            await asyncio.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))


async def _follow_stream(client: LemmaClient, conversation_id: str) -> None:
    timeout = httpx.Timeout(30.0, read=STREAM_READ_TIMEOUT_SECONDS)
    async with client.stream(
        "GET",
        f"/conversations/{conversation_id}/run/stream",
        params={"types": TERMINAL_TYPES},
        timeout=timeout,
    ) as response:
        async for _ in response.aiter_lines():
            pass
