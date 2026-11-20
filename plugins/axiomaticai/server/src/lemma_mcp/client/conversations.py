"""Finding the user's earlier conversations and reading what was said in them."""

from typing import Any

from . import LemmaClient

MATCH_MARKERS = str.maketrans("", "", "\x02\x03")


async def search(client: LemmaClient, query: str) -> list[dict[str, Any]]:
    """The user's conversations whose title, file names or messages match, best first."""
    response = await client.request("GET", "/users/me/conversations/search", params={"q": query})
    return [_hit(hit) for hit in response.json()["hits"]]


async def transcript(
    client: LemmaClient, conversation_id: str, limit: int, index: int, order: str
) -> dict[str, Any]:
    """A page of what the user typed and Lemma wrote, and how many messages there are in all."""
    params = {"limit": limit, "index": index, "order": order}
    response = await client.request(
        "GET", f"/conversations/{conversation_id}/transcript", params=params
    )
    return response.json()


def _hit(hit: dict[str, Any]) -> dict[str, Any]:
    snippet = hit["snippet"]
    return {
        "conversation_id": hit["id"],
        "title": hit["title"],
        "snippet": snippet.translate(MATCH_MARKERS) if snippet is not None else None,
        "last_message_at": hit["last_message_at"],
        "files": [f["name"] for f in hit["files"]],
        "busy": hit["run_active"],
    }
