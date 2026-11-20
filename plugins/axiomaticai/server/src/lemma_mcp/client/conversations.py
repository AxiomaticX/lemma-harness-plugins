"""Finding the user's earlier conversations and reading what was said in them."""

from typing import Any

from . import LemmaClient

MATCH_MARKERS = str.maketrans("", "", "\x02\x03")


async def search(client: LemmaClient, query: str) -> list[dict[str, Any]]:
    """The user's conversations whose title, file names or messages match, best first."""
    response = await client.request("GET", "/users/me/conversations/search", params={"q": query})
    return [_hit(hit) for hit in response.json().get("hits") or []]


async def transcript(
    client: LemmaClient, conversation_id: str, limit: int, before: int | None
) -> dict[str, Any]:
    """What the user typed and Lemma wrote, oldest first, and the cursor for earlier messages."""
    params: dict[str, Any] = {"limit": limit}
    if before is not None:
        params["before"] = before
    body = (
        await client.request("GET", f"/conversations/{conversation_id}/transcript", params=params)
    ).json()
    return {
        "messages": [
            {"source": message["source"], "text": message["text"]} for message in body["messages"]
        ],
        "before": body.get("before"),
    }


def _hit(hit: dict[str, Any]) -> dict[str, Any]:
    snippet = hit.get("snippet")
    return {
        "conversation_id": hit["id"],
        "title": hit.get("title"),
        "snippet": snippet.translate(MATCH_MARKERS) if snippet is not None else None,
        "last_message_at": hit.get("last_message_at"),
        "files": [f["name"] for f in hit.get("files") or [] if isinstance(f, dict) and "name" in f],
        "busy": bool(hit.get("run_active")),
    }
