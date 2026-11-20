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

    started = _structured(
        await server.call_tool("create_conversation", {"content": "go", "mode": "act"})
    )
    await server.call_tool(
        "send_message", {"content": "and then", "conversation_id": started["conversation_id"]}
    )

    assert opened == [started["url"]]


@pytest.mark.parametrize("opens", [True, False])
async def test_a_conversation_opens_on_request_and_its_link_comes_back_either_way(
    app: App, monkeypatch: pytest.MonkeyPatch, opens: bool
):
    opened: list[str] = []
    monkeypatch.setattr("lemma_mcp.server.webbrowser.open", lambda url: opened.append(url) or opens)

    result = _structured(
        await build_server(app).call_tool("open_in_browser", {"conversation_id": "c1"})
    )

    assert result == {"opened": opens, "url": "https://lemma.test/en/lemma/c1"}
    assert opened == ["https://lemma.test/en/lemma/c1"]


def _structured(result) -> dict:
    return result.structured_content or json.loads(result.content[0].text)


async def test_a_new_conversation_starts_in_the_mode_model_and_machine_chosen(app: App, api):
    route = api.post(url__regex=r"https://api.test/conversations/[^/]+/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )

    result = _structured(
        await build_server(app).call_tool(
            "create_conversation",
            {
                "content": "go",
                "mode": "plan",
                "model": "pro",
                "provider": "google",
                "machine": "gpu",
            },
        )
    )

    conversation_id = result["conversation_id"]
    assert result["run_id"] == "r1"
    assert result["url"] == f"https://lemma.test/en/lemma/{conversation_id}"
    assert json.loads(route.calls.last.request.content) == {
        "content": "go",
        "file_ids": [],
        "mode": "plan",
        "model": "pro",
        "provider": "google",
        "sandbox_type": "gpu",
    }


async def test_a_new_conversation_starts_on_the_users_defaults_unless_claude_names_others(
    app: App, api
):
    route = api.post(url__regex=r"https://api.test/conversations/[^/]+/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )
    server = build_server(replace(app, default_model=("google", "pro"), default_machine="gpu"))

    await server.call_tool("create_conversation", {"content": "go", "mode": "act"})
    defaulted = json.loads(route.calls.last.request.content)
    await server.call_tool(
        "create_conversation",
        {"content": "go", "mode": "act", "model": "normal", "machine": "standard"},
    )
    named = json.loads(route.calls.last.request.content)

    assert (defaulted["model"], defaulted["provider"], defaulted["sandbox_type"]) == (
        "pro",
        "google",
        "gpu",
    )
    assert (named["model"], named["provider"], named["sandbox_type"]) == (
        "normal",
        "google",
        "standard",
    )


@pytest.mark.parametrize(
    ("model", "machine", "expected"),
    [
        ("Open-weight · Normal", "High performance", (("open", "normal"), "high_performance")),
        ("", "", (None, None)),
        ("Lemma's default", "Standard", (None, "standard")),
    ],
)
def test_the_install_options_become_the_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, model, machine, expected
):
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEMMA_DEFAULT_MODEL", model)
    monkeypatch.setenv("LEMMA_DEFAULT_MACHINE", machine)

    app = App.from_env()

    assert (app.default_model, app.default_machine) == expected


async def test_a_workflow_starts_a_conversation_from_its_answers(app: App, api):
    route = api.post(url__regex=r"https://api.test/conversations/[^/]+/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r1", "started_at": None})
    )

    result = _structured(
        await build_server(app).call_tool(
            "start_workflow", {"name": "survey_literature", "inputs": {"topic": "PINNs"}}
        )
    )

    assert result["run_id"] == "r1"
    assert json.loads(route.calls.last.request.content) == {
        "file_ids": [],
        "workflow": {"name": "survey_literature", "inputs": {"topic": "PINNs"}},
    }


async def test_a_message_that_names_no_mode_or_model_keeps_the_conversations(app: App, api):
    route = api.post("https://api.test/conversations/c1/messages").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r2", "started_at": None})
    )

    await build_server(app).call_tool("send_message", {"conversation_id": "c1", "content": "more"})

    assert json.loads(route.calls.last.request.content) == {"content": "more", "file_ids": []}


async def test_an_answer_goes_on_in_a_new_run(app: App, api):
    route = api.post("https://api.test/conversations/c1/runs/r1/answers").mock(
        return_value=httpx.Response(202, json={"active": True, "run_id": "r2", "started_at": None})
    )
    answers = [{"id": "int-c1", "approved": False, "reason": "rerun it"}]

    result = _structured(
        await build_server(app).call_tool(
            "answer_questions", {"conversation_id": "c1", "run_id": "r1", "answers": answers}
        )
    )

    assert result["run_id"] == "r2"
    assert json.loads(route.calls.last.request.content) == {"answers": answers}


async def test_the_options_say_which_tiers_each_provider_runs(app: App, api):
    api.get("https://api.test/users/me/available-models").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"key": "pro_fast", "name": "Pro Fast", "is_default": False},
                {"key": "pro", "name": "Pro", "is_default": True},
            ],
        )
    )
    api.get("https://api.test/users/me/available-sandbox-types").mock(
        return_value=httpx.Response(200, json=[])
    )

    result = _structured(await build_server(app).call_tool("list_options", {}))

    assert result["providers"] == {
        "anthropic": ["pro_fast", "pro"],
        "google": ["pro"],
        "open": ["pro"],
    }


async def test_a_refused_field_is_named_in_the_error(app: App, api):
    api.post("https://api.test/conversations/c1/runs/r1/answers").mock(
        return_value=httpx.Response(
            422,
            json={"detail": [{"loc": ["body", "answers", 0, "id"], "msg": "Field required"}]},
        )
    )

    with pytest.raises(ToolError, match=r"answers\.0\.id: Field required"):
        await build_server(app).call_tool(
            "answer_questions",
            {"conversation_id": "c1", "run_id": "r1", "answers": [{"id": "q", "approved": True}]},
        )


async def test_a_plan_answer_that_fails_says_which_were_saved(app: App, api):
    api.get("https://api.test/conversations/c1/plan").mock(
        return_value=httpx.Response(200, json={"revision": 1})
    )
    api.put("https://api.test/conversations/c1/plan/questions/q1").mock(
        return_value=httpx.Response(200, json={"revision": 2})
    )
    api.put("https://api.test/conversations/c1/plan/questions/q2").mock(
        return_value=httpx.Response(404, json={"detail": "No question q2."})
    )

    with pytest.raises(ToolError, match="Answers saved before it: q1"):
        await build_server(app).call_tool(
            "answer_plan", {"conversation_id": "c1", "answers": {"q1": "yes", "q2": "no"}}
        )


async def test_the_files_list_marks_the_notebooks(app: App, api):
    api.get("https://api.test/conversations/c1").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {"id": "f1", "name": "plan_results.py", "download_url": "https://s/1"},
                    {"id": "f2", "name": "gen.py", "download_url": "https://s/2"},
                ]
            },
        )
    )
    api.get("https://api.test/conversations/c1/notebooks").mock(
        return_value=httpx.Response(200, json={"files": ["plan_results.py"], "warm": False})
    )

    result = _structured(await build_server(app).call_tool("list_files", {"conversation_id": "c1"}))

    assert [(f["name"], f["notebook"]) for f in result] == [
        ("plan_results.py", True),
        ("gen.py", False),
    ]


async def test_a_lemma_failure_reaches_the_agent_as_its_own_message(app: App, api):
    api.post("https://api.test/conversations/c1/messages").mock(return_value=httpx.Response(409))

    with pytest.raises(ToolError, match="still working on this conversation"):
        await build_server(app).call_tool(
            "send_message", {"content": "go", "conversation_id": "c1"}
        )


async def test_the_result_carries_the_link_to_the_conversation(app: App, api):
    api.get("https://api.test/conversations/c1/runs/r1").mock(
        return_value=httpx.Response(
            200,
            json={
                "outcome": "waiting_for_input",
                "answer": None,
                "questions": [{"id": "int-c1", "message": "Accept Task 1's results?"}],
            },
        )
    )

    result = _structured(
        await build_server(app).call_tool("get_result", {"conversation_id": "c1", "run_id": "r1"})
    )

    assert result == {
        "outcome": "waiting_for_input",
        "answer": None,
        "questions": [{"id": "int-c1", "message": "Accept Task 1's results?"}],
        "url": "https://lemma.test/en/lemma/c1",
    }


async def test_a_found_conversation_carries_its_link(app: App, api):
    api.get("https://api.test/users/me/conversations/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": "c1",
                        "title": "Ring sweep",
                        "snippet": None,
                        "last_message_at": None,
                        "files": [],
                        "run_active": False,
                    }
                ]
            },
        )
    )

    result = _structured(
        await build_server(app).call_tool("find_conversations", {"query": "ring sweep"})
    )

    assert [hit["url"] for hit in result] == ["https://lemma.test/en/lemma/c1"]


@pytest.mark.parametrize(
    ("asked", "sent"),
    [
        ({}, {"limit": "10", "index": "0", "order": "latest"}),
        (
            {"limit": 500, "index": 7, "order": "oldest"},
            {"limit": "100", "index": "7", "order": "oldest"},
        ),
        ({"limit": 0, "index": -3}, {"limit": "1", "index": "0", "order": "latest"}),
    ],
)
async def test_reading_a_conversation_asks_for_a_page_within_the_range(
    app: App, api, asked: dict, sent: dict
):
    route = api.get("https://api.test/conversations/c1/transcript").mock(
        return_value=httpx.Response(200, json={"messages": [], "total": 0})
    )

    await build_server(app).call_tool("read_conversation", {"conversation_id": "c1", **asked})

    assert dict(route.calls.last.request.url.params) == sent


def _long_transcript(api, chars: int) -> None:
    api.get("https://api.test/conversations/c1/transcript").mock(
        return_value=httpx.Response(
            200,
            json={
                "messages": [{"index": 0, "source": "assistant", "text": "x" * chars}],
                "total": 1,
            },
        )
    )


async def test_an_output_past_the_cap_is_cut_with_word_of_how_to_get_the_rest(app: App, api):
    _long_transcript(api, 500)

    result = await build_server(replace(app, max_output_chars=100)).call_tool(
        "read_conversation", {"conversation_id": "c1"}
    )

    text = result.content[0].text
    assert text.startswith('{\n  "messages"')
    assert "[Output cut at 100 of " in text
    assert "output_file" in text


async def test_an_output_past_the_cap_is_saved_whole_to_the_file_asked_for(
    app: App, api, tmp_path: Path
):
    _long_transcript(api, 500)
    (tmp_path / "page.json").write_text("keep me")

    result = await build_server(replace(app, max_output_chars=100)).call_tool(
        "read_conversation", {"conversation_id": "c1", "output_file": "page.json"}
    )

    saved = tmp_path / "page (1).json"
    assert json.loads(saved.read_text())["messages"][0]["text"] == "x" * 500
    assert (tmp_path / "page.json").read_text() == "keep me"
    assert str(saved) in result.content[0].text


async def test_an_output_within_the_cap_comes_back_whole_even_with_a_file_named(
    app: App, api, tmp_path: Path
):
    _long_transcript(api, 50)

    result = _structured(
        await build_server(app).call_tool(
            "read_conversation", {"conversation_id": "c1", "output_file": "page.json"}
        )
    )

    assert result["messages"][0]["text"] == "x" * 50
    assert not (tmp_path / "page.json").exists()


@pytest.mark.parametrize(("setting", "cap"), [(None, 40_000), ("", 40_000), ("5000", 5000)])
def test_the_output_cap_comes_from_the_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, setting: str | None, cap: int
):
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))
    if setting is None:
        monkeypatch.delenv("LEMMA_MAX_TOOL_OUTPUT_CHARS", raising=False)
    else:
        monkeypatch.setenv("LEMMA_MAX_TOOL_OUTPUT_CHARS", setting)

    assert App.from_env().max_output_chars == cap
