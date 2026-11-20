"""The background hook that wakes Claude when a run it started, or waited on, ends."""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from .auth import Session
from .client import LemmaClient
from .client.runs import RUNNING, wait
from .config import target
from .errors import NotFoundError, NotLoggedInError

DEFAULT_MINUTES = 60
MAX_MINUTES = 23 * 60
CHUNK_SECONDS = 600.0
RETRY_SECONDS = 60.0
WAKE_CLAUDE = 2


def hook_run(event: dict[str, Any]) -> tuple[str, str, float] | None:
    """The run to follow and for how many seconds, or None when there is nothing to wait for."""
    tool_input = event.get("tool_input") or {}
    response = _structured(event.get("tool_response"))
    if response.get("outcome", RUNNING) != RUNNING:
        return None
    conversation_id = response.get("conversation_id") or tool_input.get("conversation_id")
    run_id = response.get("run_id") or tool_input.get("run_id")
    if not conversation_id or not run_id:
        return None
    minutes = int(tool_input.get("wake_after_minutes") or DEFAULT_MINUTES)
    return str(conversation_id), str(run_id), 60.0 * max(1, min(minutes, MAX_MINUTES))


def _structured(response: Any) -> dict[str, Any]:
    """A tool's result as a dict, whichever shape the hook input carries it in."""
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except ValueError:
            return {}
    if isinstance(response, dict):
        if isinstance(response.get("structuredContent"), dict):
            return response["structuredContent"]
        if "content" in response:
            return _structured(response["content"])
        return response
    if isinstance(response, list):
        for block in response:
            if isinstance(block, dict) and block.get("type") == "text":
                found = _structured(block.get("text", ""))
                if found:
                    return found
    return {}


def finished_line(conversation_id: str, run_id: str, outcome: str) -> str:
    return (
        f"Lemma run {run_id} in conversation {conversation_id} finished: {outcome}. "
        "Read it with get_result."
    )


def still_running_line(conversation_id: str, run_id: str, seconds: float) -> str:
    return (
        f"Lemma run {run_id} in conversation {conversation_id} is still running after "
        f"{round(seconds / 60)} minutes. Call wait_for_result to keep waiting, with "
        "wake_after_minutes set higher if it will take hours."
    )


async def follow(client: LemmaClient, conversation_id: str, run_id: str, window: float) -> str:
    """The line to wake Claude with: how the run ended, or that it is still going."""
    deadline = time.monotonic() + window
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            ended = await wait(client, conversation_id, run_id, min(remaining, CHUNK_SECONDS))
        except (NotFoundError, NotLoggedInError) as e:
            return f"Stopped waiting for Lemma run {run_id} in conversation {conversation_id}: {e}"
        except Exception:
            await asyncio.sleep(min(RETRY_SECONDS, max(0.0, deadline - time.monotonic())))
            continue
        if ended.outcome != RUNNING:
            return finished_line(conversation_id, run_id, ended.outcome)
    return still_running_line(conversation_id, run_id, window)


def main() -> None:
    parser = argparse.ArgumentParser(prog="lemma-wake")
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    found = hook_run(json.load(sys.stdin))
    if found is None:
        return
    try:
        lemma = target(os.environ.get("CLAUDE_PLUGIN_OPTION_ENVIRONMENT"))
    except ValueError:
        return
    client = LemmaClient(Session(lemma, args.data_dir, interactive=False))
    print(asyncio.run(follow(client, *found)), flush=True)
    sys.exit(WAKE_CLAUDE)
