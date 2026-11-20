import json
import os
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ElicitResult, ListRootsResult, Root

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

    assert [(f["name"], f["notebook"]) for f in result["result"]] == [
        ("plan_results.py", True),
        ("gen.py", False),
    ]


async def test_a_lemma_failure_reaches_the_agent_as_its_own_message(app: App, api):
    api.post("https://api.test/conversations/c1/messages").mock(return_value=httpx.Response(409))

    with pytest.raises(ToolError, match="still working on this conversation"):
        await build_server(app).call_tool(
            "send_message", {"content": "go", "conversation_id": "c1"}
        )


@pytest.mark.parametrize("bad", ["c1/../../users/me", "c1?x=1", "c1#x", "c%2F1", ""])
async def test_an_id_that_could_reach_another_endpoint_is_refused(app: App, api, bad):
    with pytest.raises(ToolError):
        await build_server(app).call_tool("get_result", {"conversation_id": bad, "run_id": "r1"})
    assert not api.calls


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


def test_files_come_only_from_the_project_or_the_allowed_folders(app: App, tmp_path: Path):
    project, shared, outside = tmp_path / "project", tmp_path / "shared", tmp_path / "outside"
    for folder in (project, shared, outside):
        folder.mkdir()
    (project / "escape").symlink_to(outside)
    scoped = replace(app, project_dir=project, allowed_dirs=(shared,))

    assert scoped.local_path("data.csv") == project.resolve() / "data.csv"
    assert scoped.local_path(str(shared / "in.gds")) == shared.resolve() / "in.gds"
    for raw in [str(outside / "x"), "../outside/x", "escape/x", "~/.ssh/id_rsa"]:
        with pytest.raises(ToolError, match="outside the project|hidden"):
            scoped.local_path(raw)
    for raw in [".env", "keys/.ssh/id_rsa", str(shared / ".aws" / "credentials")]:
        with pytest.raises(ToolError, match="hidden"):
            scoped.local_path(raw)


async def test_an_upload_from_outside_the_project_never_reaches_lemma(app: App, api, tmp_path):
    with pytest.raises(ToolError, match="outside the project"):
        await build_server(app).call_tool(
            "send_message",
            {"conversation_id": "c1", "content": "go", "files": [str(tmp_path.parent / "x")]},
        )
    assert not api.calls


def _beside(tmp_path: Path, name: str) -> Path:
    """A folder next to the project, holding data.csv."""
    folder = tmp_path.parent / f"{tmp_path.name}-{name}"
    folder.mkdir()
    (folder / "data.csv").write_text("a,b\n")
    return folder


def _answering(action: str, allow: bool = True):
    asked: list[str] = []

    async def elicit(_context, params):
        asked.append(params.message)
        content = {"allow": allow} if action == "accept" else None
        return ElicitResult(action=action, content=content)

    return elicit, asked


async def _send(app: App, file: str, mode: str = "auto", **callbacks):
    async with Client(build_server(app), mode=mode, **callbacks) as client:
        return await client.call_tool(
            "send_message", {"conversation_id": "c1", "content": "go", "files": [file]}
        )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_files_in_the_workspace_the_client_shares_are_sent(
    app: App, api, tmp_path: Path, mode: str
):
    workspace = _beside(tmp_path, "workspace")
    uploads = api.post("https://api.test/files/").mock(return_value=httpx.Response(500))
    elicit, asked = _answering("decline")

    async def roots(_context):
        return ListRootsResult(roots=[Root(uri=workspace.as_uri())])

    result = await _send(
        app, "data.csv", mode, list_roots_callback=roots, elicitation_callback=elicit
    )

    assert uploads.called, result
    assert not asked


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_a_file_outside_the_project_is_sent_only_once_the_user_allows_it(
    app: App, api, tmp_path: Path, mode: str
):
    outside = _beside(tmp_path, "outside") / "data.csv"
    uploads = api.post("https://api.test/files/").mock(return_value=httpx.Response(500))
    elicit, asked = _answering("accept")

    result = await _send(app, str(outside), mode, elicitation_callback=elicit)

    assert uploads.called, result
    assert len(asked) == 1 and str(outside) in asked[0]


@pytest.mark.parametrize(
    ("action", "allow"), [("decline", True), ("cancel", True), ("accept", False)]
)
async def test_a_file_the_user_does_not_allow_never_reaches_lemma(
    app: App, api, tmp_path: Path, action: str, allow: bool
):
    outside = _beside(tmp_path, "outside") / "data.csv"
    elicit, asked = _answering(action, allow)

    result = await _send(app, str(outside), elicitation_callback=elicit)

    assert result.is_error and "did not allow" in result.content[0].text
    assert asked and not api.calls


async def test_a_hidden_file_is_refused_without_asking(app: App, api, tmp_path: Path):
    elicit, asked = _answering("accept")

    result = await _send(app, str(tmp_path.parent / ".ssh" / "id_rsa"), elicitation_callback=elicit)

    assert result.is_error and "hidden" in result.content[0].text
    assert not asked and not api.calls


async def test_without_a_way_to_ask_the_user_a_file_outside_is_refused(app, api, tmp_path):
    result = await _send(app, str(_beside(tmp_path, "outside") / "data.csv"))

    assert result.is_error and "LEMMA_ALLOWED_DIRS" in result.content[0].text
    assert not api.calls


async def test_saving_outside_the_project_asks_the_user_first(app: App, api, tmp_path: Path):
    elicit, asked = _answering("decline")

    async with Client(build_server(app), elicitation_callback=elicit) as client:
        result = await client.call_tool(
            "download_file",
            {"conversation_id": "c1", "name": "fit.png", "dest_dir": str(tmp_path.parent)},
        )

    assert result.is_error and "did not allow" in result.content[0].text
    assert asked and not api.calls


async def test_the_agent_cannot_supply_the_workspace_or_the_consent(app: App):
    tools = {tool.name: tool for tool in await build_server(app).list_tools()}

    for name in ["create_conversation", "send_message", "start_workflow", "download_file"]:
        assert not {"workspace", "consent"} & set(tools[name].input_schema["properties"])


def test_from_env_reads_the_allowed_folders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LEMMA_ALLOWED_DIRS", f"/data/a{os.pathsep}/data/b")

    assert App.from_env().allowed_dirs == (Path("/data/a"), Path("/data/b"))


def test_from_env_uses_plugin_data_and_antigravity_harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv("LEMMA_DATA_DIR", raising=False)
    monkeypatch.setenv("PLUGIN_DATA", str(tmp_path))
    monkeypatch.setenv("LEMMA_HARNESS", "antigravity")

    loaded = App.from_env()

    assert loaded.background_wait is True
    assert Path(loaded.client.session.store.lock.lock_file).parent == tmp_path


async def test_antigravity_mode_guides_background_wait_and_follows_wake_window(
    app: App, monkeypatch: pytest.MonkeyPatch
):
    recorded: list[tuple[str, str, float]] = []

    async def fake_wait_window(_client, conversation_id: str, run_id: str, window: float):
        recorded.append((conversation_id, run_id, window))
        from lemma_mcp.client.runs import RunResult

        return RunResult("answered", "done")

    monkeypatch.setattr("lemma_mcp.server.runs.wait_window", fake_wait_window)
    server = build_server(replace(app, background_wait=True))

    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "wait_for_result" in (server.instructions or "")
    assert "Call wait_for_result next" in (tools["create_conversation"].description or "")
    assert "Wait in the background" in (tools["wait_for_result"].description or "")

    result = _structured(
        await server.call_tool(
            "wait_for_result",
            {"conversation_id": "c1", "run_id": "r1", "wake_after_minutes": 120},
        )
    )
    await server.call_tool(
        "wait_for_result",
        {"conversation_id": "c1", "run_id": "r1", "timeout_s": 45},
    )

    assert result["outcome"] == "answered"
    assert result["answer"] == "done"
    assert recorded == [("c1", "r1", 7200.0), ("c1", "r1", 45.0)]


async def test_claude_mode_wait_for_result_uses_foreground_timeout(
    app: App, monkeypatch: pytest.MonkeyPatch
):
    seen: list[float] = []

    async def fake_wait(_client, _conversation_id: str, _run_id: str, timeout: float):
        seen.append(timeout)
        from lemma_mcp.client.runs import RunResult

        return RunResult("running", None)

    monkeypatch.setattr("lemma_mcp.server.runs.wait", fake_wait)
    server = build_server(app)

    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "You are woken when the run ends" in (tools["create_conversation"].description or "")

    await server.call_tool("wait_for_result", {"conversation_id": "c1", "run_id": "r1"})
    await server.call_tool(
        "wait_for_result", {"conversation_id": "c1", "run_id": "r1", "timeout_s": 0}
    )

    assert seen == [600, 0]


async def test_configure_persists_settings_and_applies_them_live(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    for name in (
        "LEMMA_ENVIRONMENT",
        "LEMMA_OPEN_BROWSER",
        "LEMMA_DEFAULT_MODEL",
        "LEMMA_DEFAULT_MACHINE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))

    loaded = App.from_env()
    server = build_server(loaded)

    initial = _structured(await server.call_tool("configure", {}))
    assert initial == {
        "environment": "production",
        "open_browser": True,
        "default_model": "Lemma's default",
        "default_machine": "Standard",
        "config_path": str(tmp_path / "config.json"),
    }
    assert not (tmp_path / "config.json").exists()

    updated = _structured(
        await server.call_tool(
            "configure",
            {
                "environment": "staging",
                "open_browser": False,
                "default_model": "Anthropic · Pro",
                "default_machine": "GPU",
            },
        )
    )
    assert updated == {
        "environment": "staging",
        "open_browser": False,
        "default_model": "Anthropic · Pro",
        "default_machine": "GPU",
        "config_path": str(tmp_path / "config.json"),
    }
    assert loaded.target.name == "staging"
    assert loaded.client.target.api_url == "https://api.staging.axiomatic-ai.com"

    reloaded = App.from_env()
    assert reloaded.target.name == "staging"
    assert reloaded.open_browser is False
    assert reloaded.default_model == ("anthropic", "pro")
    assert reloaded.default_machine == "gpu"

    reset_model = _structured(
        await server.call_tool("configure", {"default_model": "Lemma's default"})
    )
    assert reset_model["default_model"] == "Lemma's default"
    assert loaded.default_model is None
    await loaded.client.aclose()
    await reloaded.client.aclose()


async def test_env_vars_override_saved_config_and_configure_reports_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("LEMMA_DATA_DIR", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"environment": "staging", "open_browser": False}), encoding="utf-8"
    )
    monkeypatch.setenv("LEMMA_ENVIRONMENT", "dev")
    monkeypatch.delenv("LEMMA_OPEN_BROWSER", raising=False)
    monkeypatch.delenv("LEMMA_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LEMMA_DEFAULT_MACHINE", raising=False)

    loaded = App.from_env()
    assert loaded.target.name == "dev"
    assert loaded.open_browser is False

    shown = _structured(await build_server(loaded).call_tool("configure", {}))
    assert shown["env_overrides"] == ["LEMMA_ENVIRONMENT"]
    await loaded.client.aclose()
