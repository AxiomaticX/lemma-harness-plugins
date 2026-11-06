import asyncio
from pathlib import Path

import pytest

from lemma_mcp import watch
from lemma_mcp.client.runs import RunResult
from lemma_mcp.errors import NotFoundError, NotLoggedInError
from lemma_mcp.watch import Monitor, WatchedRun, WatchList

RUN = WatchedRun("c1", "r1", "/work/project")
OTHER_PROJECT = WatchedRun("c2", "r2", "/work/other")


def test_runs_are_watched_per_project(tmp_path: Path):
    watched = WatchList(tmp_path)
    watched.add(RUN)
    watched.add(RUN)
    watched.add(OTHER_PROJECT)

    assert watched.for_project("/work/project") == [RUN]

    watched.remove(RUN)
    assert watched.for_project("/work/project") == []
    assert watched.for_project("/work/other") == [OTHER_PROJECT]


async def test_the_monitor_reports_a_finished_run_once_and_forgets_it(
    tmp_path: Path, monkeypatch, capsys
):
    outcomes = iter([RunResult("running", None), RunResult("answered", "42")])

    async def fake_wait(_client, conversation_id, run_id, _timeout):
        assert (conversation_id, run_id) == ("c1", "r1")
        return next(outcomes)

    monkeypatch.setattr(watch, "wait", fake_wait)
    WatchList(tmp_path).add(RUN)
    WatchList(tmp_path).add(OTHER_PROJECT)
    monitor = Monitor(tmp_path, "/work/project")

    monitor.scan()
    monitor.scan()
    await asyncio.gather(*monitor._waiting.values())

    lines = capsys.readouterr().out.splitlines()
    assert lines == [watch.finished_line(RUN, "answered")]
    assert WatchList(tmp_path).for_project("/work/project") == []
    assert WatchList(tmp_path).for_project("/work/other") == [OTHER_PROJECT]


@pytest.mark.parametrize(
    "reason",
    [NotFoundError("This conversation has no run r1."), NotLoggedInError("Not signed in.")],
)
async def test_a_run_the_monitor_can_no_longer_follow_is_reported_and_dropped(
    tmp_path: Path, monkeypatch, capsys, reason
):
    async def fake_wait(*_args):
        raise reason

    monkeypatch.setattr(watch, "wait", fake_wait)
    WatchList(tmp_path).add(RUN)
    monitor = Monitor(tmp_path, "/work/project")

    monitor.scan()
    await asyncio.gather(*monitor._waiting.values())

    assert capsys.readouterr().out.splitlines() == [watch.stopped_line(RUN, reason)]
    assert WatchList(tmp_path).for_project("/work/project") == []
    assert monitor._waiting == {}


async def test_an_unexpected_failure_is_retried_rather_than_ending_the_watch(
    tmp_path: Path, monkeypatch, capsys
):
    outcomes = iter([KeyError("outcome"), RunResult("answered", "42")])

    async def fake_wait(*_args):
        result = next(outcomes)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(watch, "wait", fake_wait)
    monkeypatch.setattr(watch, "RETRY_SECONDS", 0)
    WatchList(tmp_path).add(RUN)
    monitor = Monitor(tmp_path, "/work/project")

    monitor.scan()
    await asyncio.gather(*monitor._waiting.values())

    assert capsys.readouterr().out.splitlines() == [watch.finished_line(RUN, "answered")]
