import json

import pytest

from lemma_mcp import wake
from lemma_mcp.client.runs import RunResult
from lemma_mcp.errors import NotFoundError, NotLoggedInError

SENT = {"conversation_id": "c1", "run_id": "r1", "url": "https://lemma.test/en/lemma/c1"}


def _event(tool_input: dict, tool_response) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_input": tool_input,
        "tool_response": tool_response,
    }


@pytest.mark.parametrize(
    "response",
    [
        SENT,
        {"structuredContent": SENT},
        {"content": [{"type": "text", "text": json.dumps(SENT)}]},
        [{"type": "text", "text": json.dumps(SENT)}],
        json.dumps(SENT),
    ],
    ids=["dict", "structured", "content", "blocks", "text"],
)
def test_a_sent_message_is_followed_for_an_hour_by_default(response):
    assert wake.hook_run(_event({"content": "go"}, response)) == ("c1", "r1", 3600.0)


def test_the_wait_follows_the_minutes_claude_asked_for_within_the_cap():
    assert wake.hook_run(_event({"wake_after_minutes": 300}, SENT))[2] == 300 * 60
    assert wake.hook_run(_event({"wake_after_minutes": 10**6}, SENT))[2] == wake.MAX_MINUTES * 60


def test_a_wait_that_returned_still_running_is_followed_by_its_input_ids():
    event = _event({"conversation_id": "c1", "run_id": "r1"}, {"outcome": "running"})

    assert wake.hook_run(event) == ("c1", "r1", 3600.0)


def test_a_wait_that_already_saw_the_run_end_arms_nothing():
    event = _event({"conversation_id": "c1", "run_id": "r1"}, {"outcome": "answered"})

    assert wake.hook_run(event) is None


@pytest.mark.parametrize(
    "response",
    [
        '{\n  "outcome": "answered",\n  "answer": "a long rep\n\n[Output cut at 40000 of 90000]',
        "The whole output, 90000 characters, is saved to /tmp/answer.json.",
    ],
    ids=["cut", "saved"],
)
def test_a_wait_whose_result_cannot_be_read_arms_nothing(response):
    event = _event({"conversation_id": "c1", "run_id": "r1"}, response)

    assert wake.hook_run(event) is None


async def test_a_run_that_ends_wakes_claude_with_its_outcome(monkeypatch):
    outcomes = iter([RunResult("running", None), RunResult("answered", "42")])

    async def fake_wait(_client, conversation_id, run_id, _timeout):
        assert (conversation_id, run_id) == ("c1", "r1")
        return next(outcomes)

    monkeypatch.setattr(wake, "wait", fake_wait)

    assert await wake.follow(None, "c1", "r1", 3600) == wake.finished_line("c1", "r1", "answered")


async def test_a_run_still_going_at_the_end_of_the_window_says_so(monkeypatch):
    async def fake_wait(*_args):
        return RunResult("running", None)

    monkeypatch.setattr(wake, "wait", fake_wait)

    assert await wake.follow(None, "c1", "r1", 0.01) == wake.still_running_line("c1", "r1", 0.01)


@pytest.mark.parametrize(
    "reason",
    [NotFoundError("This conversation has no run r1."), NotLoggedInError("Not signed in.")],
)
async def test_a_run_that_can_no_longer_be_followed_wakes_claude_with_why(monkeypatch, reason):
    async def fake_wait(*_args):
        raise reason

    monkeypatch.setattr(wake, "wait", fake_wait)

    assert str(reason) in await wake.follow(None, "c1", "r1", 3600)


async def test_an_unexpected_failure_is_retried_rather_than_ending_the_wait(monkeypatch):
    outcomes = iter([KeyError("outcome"), RunResult("answered", "42")])

    async def fake_wait(*_args):
        result = next(outcomes)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(wake, "wait", fake_wait)
    monkeypatch.setattr(wake, "RETRY_SECONDS", 0)

    assert await wake.follow(None, "c1", "r1", 3600) == wake.finished_line("c1", "r1", "answered")
