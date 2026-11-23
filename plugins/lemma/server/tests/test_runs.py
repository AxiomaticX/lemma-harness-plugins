import json

import httpx
import pytest
from conftest import TOKEN_URL, token_response

from lemma_mcp.client import LemmaClient, runs
from lemma_mcp.errors import LemmaError, NotFoundError, ServerError, UsageLimitError

RUN = "https://api.test/conversations/c1/runs/r1"
STREAM = "https://api.test/conversations/c1/run/stream"


def _result(outcome: str, answer: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"outcome": outcome, "answer": answer})


def _sse(*events: dict) -> httpx.Response:
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events)
    return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    monkeypatch.setattr(runs, "POLL_SECONDS", 0.01)


async def test_send_posts_the_message_and_returns_its_run(client: LemmaClient, api):
    route = api.post("https://api.test/conversations/c1/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )

    run_id = await runs.send(client, "c1", "fit this", ["f1"], {"plan_mode": False})

    assert run_id == "r1"
    assert route.calls.last.request.extensions["timeout"]["read"] == runs.SEND_READ_TIMEOUT_SECONDS
    assert json.loads(route.calls.last.request.content) == {
        "content": "fit this",
        "file_ids": ["f1"],
        "plan_mode": False,
    }


async def test_a_finished_run_is_reported_without_opening_the_stream(client: LemmaClient, api):
    api.get(RUN).mock(return_value=_result("answered", "42"))
    stream = api.get(STREAM)

    ended = await runs.wait(client, "c1", "r1", timeout=60)

    assert ended == runs.RunResult("answered", "42")
    assert not stream.called


async def test_the_runs_own_finish_on_the_stream_ends_the_wait(client: LemmaClient, api):
    api.get(RUN).mock(side_effect=[_result("running"), _result("answered", "42")])
    stream = api.get(STREAM).mock(return_value=_sse({"type": "RUN_FINISHED", "runId": "r1"}))

    assert await runs.wait(client, "c1", "r1", timeout=60) == runs.RunResult("answered", "42")
    assert stream.calls.last.request.url.params["types"] == "RUN_FINISHED,RUN_ERROR"


@pytest.mark.parametrize(
    "stream",
    [
        _sse(),
        _sse({"type": "CUSTOM", "name": "something_else"}),
        _sse({"type": "RUN_STARTED", "runId": "someone-else"}),
    ],
    ids=["empty at once", "an unrelated event", "another run"],
)
async def test_a_stream_that_says_nothing_about_the_run_falls_back_to_the_stored_result(
    client: LemmaClient, api, stream
):
    api.get(RUN).mock(side_effect=[_result("running"), _result("running"), _result("no_answer")])
    api.get(STREAM).mock(return_value=stream)

    assert (await runs.wait(client, "c1", "r1", timeout=60)).outcome == "no_answer"


async def test_an_http_error_on_the_stream_is_resolved_from_the_stored_result(
    client: LemmaClient, api
):
    api.get(RUN).mock(side_effect=[_result("running"), _result("answered", "ok")])
    api.get(STREAM).mock(return_value=httpx.Response(502))

    assert (await runs.wait(client, "c1", "r1", timeout=60)).answer == "ok"


async def test_a_dropped_stream_is_resolved_from_the_stored_result(client: LemmaClient, api):
    api.get(RUN).mock(side_effect=[_result("running"), _result("waiting_for_input")])
    api.get(STREAM).mock(side_effect=httpx.ReadError("connection reset"))

    assert (await runs.wait(client, "c1", "r1", timeout=60)).outcome == "waiting_for_input"


async def test_a_wait_that_runs_out_reports_the_run_still_running(client: LemmaClient, api):
    api.get(RUN).mock(return_value=_result("running"))
    api.get(STREAM).mock(return_value=_sse())

    assert (await runs.wait(client, "c1", "r1", timeout=0.05)).outcome == "running"


async def test_the_stream_refreshes_a_rejected_token(client: LemmaClient, api):
    api.post(TOKEN_URL).mock(
        side_effect=[token_response("at-1", "rt-2"), token_response("at-2", "rt-3")]
    )
    api.get(RUN).mock(side_effect=[_result("running"), _result("answered", "ok")])
    stream = api.get(STREAM).mock(
        side_effect=[httpx.Response(401), _sse({"type": "RUN_FINISHED", "runId": "r1"})]
    )

    assert (await runs.wait(client, "c1", "r1", timeout=60)).answer == "ok"
    assert stream.calls.last.request.headers["Authorization"] == "Bearer at-2"


async def test_wait_window_follows_chunks_and_retries_transient_errors(client: LemmaClient):
    outcomes = iter(
        [
            httpx.ConnectError("down"),
            ServerError("Lemma returned an error: HTTP 503"),
            runs.RunResult("running", None),
            runs.RunResult("answered", "7"),
        ]
    )

    async def fake_wait(_client, _conversation_id, _run_id, _timeout):
        item = next(outcomes)
        if isinstance(item, Exception):
            raise item
        return item

    ended = await runs.wait_window(
        client, "c1", "r1", 30.0, chunk_seconds=10.0, retry_seconds=0.0, wait_fn=fake_wait
    )

    assert ended == runs.RunResult("answered", "7")


@pytest.mark.parametrize(
    "failure",
    [
        LemmaError("Lemma returned an error: Forbidden"),
        UsageLimitError(),
        NotFoundError("No such run."),
        KeyError("outcome"),
    ],
)
async def test_wait_window_raises_any_other_failure_at_once(
    client: LemmaClient, failure: Exception
):
    calls = 0

    async def fake_wait(_client, _conversation_id, _run_id, _timeout):
        nonlocal calls
        calls += 1
        raise failure

    with pytest.raises(type(failure)):
        await runs.wait_window(
            client, "c1", "r1", 30.0, chunk_seconds=10.0, retry_seconds=0.0, wait_fn=fake_wait
        )
    assert calls == 1


async def test_wait_window_with_zero_window_checks_once(client: LemmaClient):
    calls: list[float] = []

    async def fake_wait(_client, _conversation_id, _run_id, timeout):
        calls.append(timeout)
        return runs.RunResult("running", None)

    ended = await runs.wait_window(client, "c1", "r1", 0.0, wait_fn=fake_wait)

    assert ended.outcome == "running"
    assert calls == [0.0]
