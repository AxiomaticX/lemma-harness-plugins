import json
import tomllib
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from mcp import Client

from lemma_mcp import unwaited
from lemma_mcp.client import LemmaClient
from lemma_mcp.client.runs import RunResult
from lemma_mcp.server import App, build_server

PLUGIN = Path(__file__).parents[2]
CALLER = {unwaited.CALLER_META_KEY: "agy-1"}


@pytest.fixture
def app(client: LemmaClient, tmp_path: Path) -> App:
    return App(
        target=client.target,
        client=client,
        project_dir=tmp_path,
        open_browser=False,
        antigravity=True,
        unwaited_dir=tmp_path / "unwaited",
    )


def test_the_stop_hook_names_every_run_without_a_wait(tmp_path: Path):
    unwaited.record(tmp_path, "agy-1", "c1", "r1")
    unwaited.record(tmp_path, "agy-1", "c2", "r2")
    unwaited.record(tmp_path, "agy-2", "c3", "r3")

    decided = unwaited.decide({"conversationId": "agy-1", "continuationActive": False}, tmp_path)

    assert decided["decision"] == "continue"
    assert "conversation_id c1, run_id r1" in decided["reason"]
    assert "conversation_id c2, run_id r2" in decided["reason"]
    assert "r3" not in decided["reason"]


@pytest.mark.parametrize(
    "event",
    [
        {"conversationId": "agy-1", "continuationActive": True},
        {"conversationId": "agy-other", "continuationActive": False},
        {"conversationId": "../agy-1", "continuationActive": False},
        {},
    ],
)
def test_the_stop_hook_lets_the_turn_end(tmp_path: Path, event: dict):
    unwaited.record(tmp_path, "agy-1", "c1", "r1")

    assert unwaited.decide(event, tmp_path) == {}


async def test_a_started_run_stays_unwaited_until_a_wait_ends_it(
    app: App, api, monkeypatch: pytest.MonkeyPatch
):
    api.post("https://api.test/conversations/c1/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )
    outcomes = iter([RunResult("running", None), RunResult("answered", "done")])

    async def fake_wait_window(_client, _conversation_id, _run_id, _window):
        assert unwaited.pending(app.unwaited_dir, "agy-1") == []
        return next(outcomes)

    monkeypatch.setattr("lemma_mcp.server.runs.wait_window", fake_wait_window)
    waiting = {"conversation_id": "c1", "run_id": "r1"}
    message = {"conversation_id": "c1", "content": "go"}

    async with Client(build_server(app)) as client:
        await client.call_tool("send_message", message, meta=CALLER)
        assert unwaited.pending(app.unwaited_dir, "agy-1") == [waiting]

        await client.call_tool("wait_for_result", waiting, meta=CALLER)
        assert unwaited.pending(app.unwaited_dir, "agy-1") == [waiting]

        await client.call_tool("wait_for_result", waiting, meta=CALLER)
        assert unwaited.pending(app.unwaited_dir, "agy-1") == []


async def test_claude_code_records_no_runs(app: App, api):
    api.post("https://api.test/conversations/c1/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )
    claude = replace(app, antigravity=False, unwaited_dir=None)
    message = {"conversation_id": "c1", "content": "go"}

    async with Client(build_server(claude)) as client:
        await client.call_tool("send_message", message, meta=CALLER)

    assert not app.unwaited_dir.exists()


def test_the_antigravity_stop_hook_runs_the_unwaited_check():
    scripts = tomllib.loads((PLUGIN / "server" / "pyproject.toml").read_text())["project"]
    hooks = json.loads((PLUGIN / "hooks.json").read_text())

    (handler,) = hooks["lemma-unwaited-runs"]["Stop"]
    assert handler["command"].split()[-1] in scripts["scripts"]
    assert scripts["scripts"]["lemma-unwaited"] == "lemma_mcp.unwaited:main"
