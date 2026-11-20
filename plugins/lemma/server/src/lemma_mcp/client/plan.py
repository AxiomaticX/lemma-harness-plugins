"""A conversation's plan: read, edit, answer, approve, review and run it, and manage its tasks."""

from typing import Any

import httpx

from ..errors import LemmaError
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
    answered: list[str] = []
    for question_id, text in answers.items():
        try:
            response = await client.request(
                "PUT",
                _path(conversation_id, f"/questions/{question_id}"),
                json={"answer": text, "revision": plan["revision"]},
            )
        except LemmaError as e:
            saved = ", ".join(answered) or "none"
            raise LemmaError(f"{e} Answers saved before it: {saved}.") from e
        plan = response.json()
        answered.append(question_id)
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
    return await _on_current(
        client,
        conversation_id,
        f"/tasks/{task_id}/review",
        {"decision": decision, "reason": reason},
    )


async def edit(
    client: LemmaClient,
    conversation_id: str,
    revision: int,
    overview: str,
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace the plan's definition as of ``revision``, the one the edit was made from."""
    response = await client.request(
        "PUT",
        _path(conversation_id),
        json={"revision": revision, "overview": overview, "tasks": tasks},
    )
    return response.json()


async def _on_current(
    client: LemmaClient, conversation_id: str, rest: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    plan = await get(client, conversation_id)
    response = await client.request(
        "POST", _path(conversation_id, rest), json={**(body or {}), "revision": plan["revision"]}
    )
    return response.json()


async def delete_task(
    client: LemmaClient, conversation_id: str, task_id: str, keep_dependents: bool
) -> dict[str, Any]:
    return await _on_current(
        client, conversation_id, f"/tasks/{task_id}/delete", {"keep_dependents": keep_dependents}
    )


async def reopen_task(client: LemmaClient, conversation_id: str, task_id: str) -> dict[str, Any]:
    return await _on_current(client, conversation_id, f"/tasks/{task_id}/reset")


async def set_task_checks(
    client: LemmaClient, conversation_id: str, task_id: str, enabled: bool
) -> dict[str, Any]:
    return await _on_current(
        client, conversation_id, f"/tasks/{task_id}/validation", {"disabled": not enabled}
    )


async def revisions(client: LemmaClient, conversation_id: str) -> list[dict[str, Any]]:
    return (await client.request("GET", _path(conversation_id, "/revisions"))).json()


async def restore(client: LemmaClient, conversation_id: str, number: int) -> dict[str, Any]:
    return await _on_current(client, conversation_id, f"/revisions/{number}/restore")


async def delete(client: LemmaClient, conversation_id: str) -> None:
    await client.request("DELETE", _path(conversation_id))


async def run(client: LemmaClient, conversation_id: str, scope: str) -> str:
    """Start running the approved plan; returns the run id."""
    response = await client.request(
        "POST",
        _path(conversation_id, "/run"),
        json={"scope": scope},
        timeout=httpx.Timeout(30.0, read=SEND_READ_TIMEOUT_SECONDS),
    )
    return response.json()["run_id"]
