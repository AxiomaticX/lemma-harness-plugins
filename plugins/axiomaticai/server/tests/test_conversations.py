import httpx

from lemma_mcp.client import LemmaClient, conversations

SEARCH = "https://api.test/users/me/conversations/search"
TRANSCRIPT = "https://api.test/conversations/c1/transcript"


def _hit(**overrides) -> dict:
    return {
        "id": "c1",
        "user_id": "u1",
        "agent": "lemma",
        "title": "Ring resonator sweep",
        "status": "active",
        "files": [{"id": "f1", "name": "sweep.py", "download_url": "https://storage.test/x"}],
        "last_message_at": "2026-11-01T10:00:00Z",
        "created_at": "2026-10-30T10:00:00Z",
        "updated_at": "2026-11-01T10:00:00Z",
        "run_active": False,
        "training_excluded": False,
        "shared_at": None,
        "snippet": "the \x02ring\x03 loss is lowest at 5 um",
        **overrides,
    }


async def test_a_search_sends_the_query_and_keeps_only_what_claude_needs(client: LemmaClient, api):
    route = api.get(SEARCH).mock(return_value=httpx.Response(200, json={"hits": [_hit()]}))

    hits = await conversations.search(client, "ring loss")

    assert route.calls.last.request.url.params["q"] == "ring loss"
    assert hits == [
        {
            "conversation_id": "c1",
            "title": "Ring resonator sweep",
            "snippet": "the ring loss is lowest at 5 um",
            "last_message_at": "2026-11-01T10:00:00Z",
            "files": ["sweep.py"],
            "busy": False,
        }
    ]


async def test_a_hit_that_matched_only_its_title_has_no_snippet(client: LemmaClient, api):
    api.get(SEARCH).mock(
        return_value=httpx.Response(200, json={"hits": [_hit(snippet=None, run_active=True)]})
    )

    (hit,) = await conversations.search(client, "resonator")

    assert hit["snippet"] is None
    assert hit["busy"] is True


async def test_no_match_is_an_empty_list(client: LemmaClient, api):
    api.get(SEARCH).mock(return_value=httpx.Response(200, json={"hits": []}))

    assert await conversations.search(client, "grating") == []


async def test_a_transcript_page_asks_for_its_place_and_comes_back_with_the_total(
    client: LemmaClient, api
):
    page = {
        "messages": [
            {"index": 43, "source": "assistant", "text": "Here is the plot."},
            {"index": 42, "source": "user", "text": "now plot it"},
        ],
        "total": 44,
    }
    route = api.get(TRANSCRIPT).mock(return_value=httpx.Response(200, json=page))

    found = await conversations.transcript(client, "c1", limit=2, index=0, order="latest")

    assert dict(route.calls.last.request.url.params) == {
        "limit": "2",
        "index": "0",
        "order": "latest",
    }
    assert found == page
