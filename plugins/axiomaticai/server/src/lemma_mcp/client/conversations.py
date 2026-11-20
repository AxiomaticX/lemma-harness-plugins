"""Finding the user's earlier conversations and reading what was said in them."""

from typing import Any

from . import LemmaClient

MATCH_MARKERS = str.maketrans("", "", "\x02\x03")


async def search(client: LemmaClient, query: str) -> list[dict[str, Any]]:
    """The user's conversations whose title, file names or messages match, best first."""
    response = await client.request("GET", "/users/me/conversations/search", params={"q": query})
    return [_hit(hit) for hit in response.json()["hits"]]


async def recent(client: LemmaClient, limit: int) -> list[dict[str, Any]]:
    """The user's conversations, and those colleagues shared that the user took part in, most
    recently active first."""
    listed = (await client.request("GET", "/users/me/conversations")).json()["conversations"]
    newest = sorted(listed, key=lambda c: c["last_message_at"] or c["created_at"], reverse=True)
    return [_listed(item) for item in newest[:limit]]


async def transcript(
    client: LemmaClient, conversation_id: str, limit: int, index: int, order: str
) -> dict[str, Any]:
    """A page of what the user typed and Lemma wrote, and how many messages there are in all."""
    params = {"limit": limit, "index": index, "order": order}
    response = await client.request(
        "GET", f"/conversations/{conversation_id}/transcript", params=params
    )
    return response.json()


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": item["id"],
        "title": item["title"],
        "last_message_at": item["last_message_at"],
        "files": [f["name"] for f in item["files"]],
        "busy": item["run_active"],
    }


def _hit(hit: dict[str, Any]) -> dict[str, Any]:
    snippet = hit["snippet"]
    return {
        **_summary(hit),
        "snippet": snippet.translate(MATCH_MARKERS) if snippet is not None else None,
    }


def _listed(item: dict[str, Any]) -> dict[str, Any]:
    owner = item["owner"]
    return {**_summary(item), "shared_by": owner["email"] if owner else None}
