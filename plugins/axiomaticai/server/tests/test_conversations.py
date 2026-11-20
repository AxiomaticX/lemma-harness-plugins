import json
from pathlib import Path

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from lemma_mcp.client import LemmaClient, conversations
from lemma_mcp.server import App, build_server

SEARCH = "https://api.test/users/me/conversations/search"
LIST = "https://api.test/users/me/conversations"
CONVERSATION = "https://api.test/conversations/c1"


def _item(id_: str, title: str, last: str | None, **extra) -> dict:
    return {
        "id": id_,
        "user_id": "u1",
        "agent": "axiomatic",
        "title": title,
        "status": "active",
        "files": [{"id": "f1", "name": "coupler.gds"}],
        "last_message_at": last,
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        **extra,
    }


def _request(text: str) -> dict:
    return {"kind": "request", "parts": [{"part_kind": "user-prompt", "content": text}]}


def _response(*parts: dict) -> dict:
    return {"kind": "response", "parts": list(parts)}


@pytest.fixture
def app(client: LemmaClient, tmp_path: Path) -> App:
    return App(target=client.target, client=client, project_dir=tmp_path, open_browser=False)


def _structured(result) -> dict:
    return result.structured_content or json.loads(result.content[0].text)


async def test_search_sends_the_query_and_marks_the_matched_words(app: App, api):
    route = api.get(SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": [
                    _item(
                        "c1",
                        "Grating coupler",
                        "2026-10-02T00:00:00Z",
                        snippet="the \x02grating\x03 \x02coupler\x03 efficiency is 61%",
                    ),
                    _item("c2", "Coupler notes", None, snippet=None),
                ]
            },
        )
    )

    result = _structured(
        await build_server(app).call_tool("search_conversations", {"query": " grating coupler "})
    )["result"]

    assert route.calls.last.request.url.params["q"] == "grating coupler"
    assert result[0]["snippet"] == "the «grating» «coupler» efficiency is 61%"
    assert result[0]["url"] == "https://lemma.test/en/lemma/c1"
    assert result[0]["files"] == ["coupler.gds"]
    assert result[1]["snippet"] is None


@pytest.mark.parametrize("query", ["x", " ", "y" * 201])
async def test_search_refuses_a_query_lemma_would_not_run(app: App, api, query: str):
    route = api.get(SEARCH)

    with pytest.raises(ToolError, match="2 to 200 characters"):
        await build_server(app).call_tool("search_conversations", {"query": query})
    assert not route.called


async def test_list_gives_the_newest_first_up_to_the_limit_and_names_who_shared(app: App, api):
    api.get(LIST).mock(
        return_value=httpx.Response(
            200,
            json={
                "conversations": [
                    _item("old", "Old", "2026-09-01T00:00:00Z"),
                    _item("new", "New", "2026-11-01T00:00:00Z"),
                    _item(
                        "shared",
                        "Shared",
                        "2026-10-01T00:00:00Z",
                        owner={"id": "u2", "email": "colleague@example.com"},
                    ),
                ],
                "total": 3,
            },
        )
    )

    result = _structured(await build_server(app).call_tool("list_conversations", {"limit": 2}))[
        "result"
    ]

    assert [c["id"] for c in result] == ["new", "shared"]
    assert result[1]["owner"] == "colleague@example.com"
    assert result[0]["owner"] is None


async def test_read_keeps_only_what_the_user_typed_and_lemma_wrote(app: App, api):
    route = api.get(CONVERSATION).mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Grating coupler",
                "total_messages": 5,
                "next_cursor": None,
                "messages": [
                    _request('{"message": "simulate the coupler"}'),
                    _response(
                        {"part_kind": "thinking", "content": "hmm"},
                        {"part_kind": "tool-call", "tool_name": "run", "args": {}},
                    ),
                    {
                        "kind": "request",
                        "parts": [{"part_kind": "tool-return", "content": "secret tool output"}],
                    },
                    _response({"part_kind": "text", "content": "Efficiency is 61%."}),
                    "not a message",
                ],
            },
        )
    )

    result = _structured(
        await build_server(app).call_tool("read_conversation", {"conversation_id": "c1"})
    )

    assert route.calls.last.request.url.params["messages_limit"] == str(conversations.READ_BATCH)
    assert "messages_before" not in route.calls.last.request.url.params
    assert result["messages"] == [
        {"from": "user", "text": "simulate the coupler"},
        {"from": "lemma", "text": "Efficiency is 61%."},
    ]
    assert result["url"] == "https://lemma.test/en/lemma/c1"
    assert result["earlier"] is None


async def test_read_goes_further_back_from_earlier(app: App, api):
    route = api.get(CONVERSATION).mock(
        return_value=httpx.Response(
            200, json={"title": "t", "total_messages": 300, "next_cursor": 100, "messages": []}
        )
    )

    result = _structured(
        await build_server(app).call_tool(
            "read_conversation", {"conversation_id": "c1", "before": 200}
        )
    )

    assert route.calls.last.request.url.params["messages_before"] == "200"
    assert result["earlier"] == 100


def test_a_very_long_message_is_cut_and_says_how_much_was_left_out():
    long = "a" * (conversations.MAX_TEXT_CHARS + 10)

    role, text = conversations.prose(_response({"part_kind": "text", "content": long}))

    assert role == "lemma"
    assert text.endswith("[... 10 more characters]")


async def test_a_missing_conversation_is_reported(app: App, api):
    api.get(CONVERSATION).mock(
        return_value=httpx.Response(404, json={"detail": "Conversation not found"})
    )

    with pytest.raises(ToolError, match="Conversation not found"):
        await build_server(app).call_tool("read_conversation", {"conversation_id": "c1"})
