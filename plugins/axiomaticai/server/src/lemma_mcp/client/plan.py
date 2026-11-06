"""A conversation's plan: read it, answer its questions, approve it, review its tasks, run it."""

from typing import Any

import httpx

from . import LemmaClient
from .runs import SEND_READ_TIMEOUT_SECONDS


def _path(conversation_id: str, rest: str = "") -> str:
    return f"/conversations/{conversation_id}/plan{rest}"


async def get(client: LemmaClient, conversation_id: str) -> dict[str, Any]:
    return (await client.request("GET", _path(conversation_id))).json()


async def answer(
    client: LemmaClient, conversation_id: str, answers: dict[str, str], approve: bool
) -> dict[str, Any]:
    """Answer the plan's questions in turn, then approve what they produced if asked to."""
    plan = await get(client, conversation_id)
    for question_id, text in answers.items():
        plan = (
            await client.request(
                "PUT",
                _path(conversation_id, f"/questions/{question_id}"),
                json={"answer": text, "revision": plan["revision"]},
            )
        ).json()
    if approve:
        plan = (
            await client.request(
                "POST", _path(conversation_id, "/approve"), json={"revision": plan["revision"]}
            )
        ).json()
    return plan


async def review(
    client: LemmaClient, conversation_id: str, task_id: str, decision: str, reason: str
) -> dict[str, Any]:
    plan = await get(client, conversation_id)
    response = await client.request(
        "POST",
        _path(conversation_id, f"/tasks/{task_id}/review"),
        json={"decision": decision, "reason": reason, "revision": plan["revision"]},
    )
    return response.json()


async def run(client: LemmaClient, conversation_id: str, scope: str) -> str:
    """Start running the approved plan; returns the run id."""
    response = await client.request(
        "POST",
        _path(conversation_id, "/run"),
        json={"scope": scope},
        timeout=httpx.Timeout(30.0, read=SEND_READ_TIMEOUT_SECONDS),
    )
    return response.json()["run_id"]
