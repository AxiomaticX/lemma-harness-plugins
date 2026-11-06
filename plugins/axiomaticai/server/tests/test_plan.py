import json

import httpx

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


async def test_running_the_plan_returns_its_run(client: LemmaClient, api):
    route = api.post(f"{PLAN}/run").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r9", "started_at": None})
    )

    assert await plan.run(client, "c1", "next") == "r9"
    assert json.loads(route.calls.last.request.content) == {"scope": "next"}
