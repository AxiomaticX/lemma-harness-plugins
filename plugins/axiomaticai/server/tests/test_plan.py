import json

import httpx
import pytest

from lemma_mcp.client import LemmaClient, plan

PLAN = "https://api.test/conversations/c1/plan"


def _plan(revision: int, status: str = "draft") -> httpx.Response:
    return httpx.Response(200, json={"status": status, "revision": revision, "tasks": []})


async def test_answers_go_in_one_by_one_each_on_the_revision_the_last_produced(
    client: LemmaClient, api
):
    api.get(PLAN).mock(return_value=_plan(3))
    first = api.put(f"{PLAN}/questions/q1").mock(return_value=_plan(4))
    second = api.put(f"{PLAN}/questions/q2").mock(return_value=_plan(5))
    approve = api.post(f"{PLAN}/approve").mock(return_value=_plan(5, "approved"))

    result = await plan.answer(client, "c1", {"q1": "RK45", "q2": "0.9 to 1.5"}, approve=True)

    assert json.loads(first.calls.last.request.content) == {"answer": "RK45", "revision": 3}
    assert json.loads(second.calls.last.request.content) == {"answer": "0.9 to 1.5", "revision": 4}
    assert json.loads(approve.calls.last.request.content) == {"revision": 5}
    assert result["status"] == "approved"


async def test_answers_without_approval_leave_the_plan_a_draft(client: LemmaClient, api):
    api.get(PLAN).mock(return_value=_plan(3))
    api.put(f"{PLAN}/questions/q1").mock(return_value=_plan(4))
    approve = api.post(f"{PLAN}/approve")

    await plan.answer(client, "c1", {"q1": "RK45"}, approve=False)

    assert not approve.called


async def test_a_review_is_decided_on_the_current_revision(client: LemmaClient, api):
    api.get(PLAN).mock(return_value=_plan(7))
    route = api.post(f"{PLAN}/tasks/t1/review").mock(return_value=_plan(8))

    await plan.review(client, "c1", "t1", "waive", "close enough")

    assert json.loads(route.calls.last.request.content) == {
        "decision": "waive",
        "reason": "close enough",
        "revision": 7,
    }


async def test_an_edit_goes_in_on_the_revision_it_was_made_from(client: LemmaClient, api):
    route = api.put(PLAN).mock(return_value=_plan(5))
    tasks = [
        {"id": "t1", "name": "Sweep", "description": "Finely."},
        {"name": "Plot", "description": "It."},
    ]

    await plan.edit(client, "c1", 4, "Find chaos.", tasks)

    assert json.loads(route.calls.last.request.content) == {
        "revision": 4,
        "overview": "Find chaos.",
        "tasks": tasks,
    }


@pytest.mark.parametrize(
    ("call", "path", "body"),
    [
        (
            lambda c: plan.delete_task(c, "c1", "t1", True),
            "/tasks/t1/delete",
            {"keep_dependents": True},
        ),
        (lambda c: plan.reopen_task(c, "c1", "t1"), "/tasks/t1/reset", {}),
        (
            lambda c: plan.set_task_checks(c, "c1", "t1", False),
            "/tasks/t1/validation",
            {"disabled": True},
        ),
        (lambda c: plan.restore(c, "c1", 2), "/revisions/2/restore", {}),
    ],
)
async def test_a_task_or_revision_change_goes_in_on_the_current_revision(
    client: LemmaClient, api, call, path, body
):
    api.get(PLAN).mock(return_value=_plan(7))
    route = api.post(f"{PLAN}{path}").mock(return_value=_plan(8))

    await call(client)

    assert json.loads(route.calls.last.request.content) == {**body, "revision": 7}


async def test_the_plan_is_deleted(client: LemmaClient, api):
    route = api.delete(PLAN).mock(return_value=httpx.Response(204))

    await plan.delete(client, "c1")

    assert route.called


async def test_running_the_plan_returns_its_run(client: LemmaClient, api):
    route = api.post(f"{PLAN}/run").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r9", "started_at": None})
    )

    assert await plan.run(client, "c1", "next") == "r9"
    assert json.loads(route.calls.last.request.content) == {"scope": "next"}
