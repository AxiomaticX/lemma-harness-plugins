import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from lemma_mcp.client import LemmaClient
from lemma_mcp.server import App, build_server


@pytest.fixture
def app(client: LemmaClient, tmp_path: Path) -> App:
    return App(
        target=client.target,
        client=client,
        project_dir=tmp_path,
        open_browser=False,
    )


@pytest.mark.parametrize(("setting", "opens"), [(None, True), ("", True), ("false", False)])
def test_conversations_open_in_the_browser_unless_turned_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, setting: str | None, opens: bool
):
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))
    if setting is None:
        monkeypatch.delenv("LEMMA_OPEN_BROWSER", raising=False)
    else:
        monkeypatch.setenv("LEMMA_OPEN_BROWSER", setting)

    assert App.from_env().open_browser is opens


async def test_only_a_new_conversation_opens_in_the_browser(
    app: App, api, monkeypatch: pytest.MonkeyPatch
):
    api.post(url__regex=r"https://api.test/conversations/[^/]+/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )
    opened: list[str] = []
    monkeypatch.setattr("lemma_mcp.server.webbrowser.open", opened.append)
    server = build_server(replace(app, open_browser=True))

    started = _structured(await server.call_tool("send_message", {"content": "go"}))
    await server.call_tool(
        "send_message", {"content": "and then", "conversation_id": started["conversation_id"]}
    )

    assert opened == [started["url"]]


def _structured(result) -> dict:
    return result.structured_content or json.loads(result.content[0].text)


async def test_a_new_conversation_is_started(app: App, api):
    route = api.post(url__regex=r"https://api.test/conversations/[^/]+/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )

    result = _structured(
        await build_server(app).call_tool("send_message", {"content": "go", "machine": "gpu"})
    )

    conversation_id = result["conversation_id"]
    assert result["run_id"] == "r1"
    assert result["url"] == f"https://lemma.test/en/lemma/{conversation_id}"
    assert json.loads(route.calls.last.request.content) == {
        "content": "go",
        "file_ids": [],
        "plan_mode": False,
        "sandbox_type": "gpu",
    }


async def test_a_lemma_failure_reaches_the_agent_as_its_own_message(app: App, api):
    api.post("https://api.test/conversations/c1/messages").mock(return_value=httpx.Response(409))

    with pytest.raises(ToolError, match="still working on this conversation"):
        await build_server(app).call_tool(
            "send_message", {"content": "go", "conversation_id": "c1"}
        )


async def test_the_result_carries_the_link_to_the_conversation(app: App, api):
    api.get("https://api.test/conversations/c1/runs/r1").mock(
        return_value=httpx.Response(200, json={"outcome": "waiting_for_input", "answer": None})
    )

    result = _structured(
        await build_server(app).call_tool("get_result", {"conversation_id": "c1", "run_id": "r1"})
    )

    assert result == {
        "outcome": "waiting_for_input",
        "answer": None,
        "url": "https://lemma.test/en/lemma/c1",
    }
