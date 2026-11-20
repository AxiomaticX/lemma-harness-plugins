"""Finding the user's earlier Lemma conversations and reading what was said in them."""

import json
from typing import Any

from . import LemmaClient

READ_BATCH = 100
MAX_TEXT_CHARS = 20_000
MATCH_START, MATCH_END = "\x02", "\x03"
_PROSE_PARTS = {"request": ("user-prompt", "user"), "response": ("text", "lemma")}


async def search(client: LemmaClient, query: str) -> list[dict[str, Any]]:
    """The user's conversations whose title, file names or messages match, best first."""
    response = await client.request(
        "GET", "/users/me/conversations/search", params={"q": query.strip()}
    )
    return [
        {**_summary(hit), "snippet": _marked(hit.get("snippet"))}
        for hit in response.json().get("hits") or []
    ]


async def recent(client: LemmaClient, limit: int) -> list[dict[str, Any]]:
    """The user's conversations, and those colleagues shared that they took part in, newest
    first."""
    listed = (await client.request("GET", "/users/me/conversations")).json()
    items = sorted(
        listed.get("conversations") or [],
        key=lambda c: c.get("last_message_at") or c.get("created_at") or "",
        reverse=True,
    )
    return [_summary(item) for item in items[: max(limit, 0)]]


async def read(client: LemmaClient, conversation_id: str, before: int | None) -> dict[str, Any]:
    """The prose of a conversation's latest stored messages, or of those before ``before``."""
    params: dict[str, Any] = {"messages_limit": READ_BATCH}
    if before is not None:
        params["messages_before"] = before
    body = (await client.request("GET", f"/conversations/{conversation_id}", params=params)).json()
    stored = body.get("messages") or []
    messages = []
    for message in stored:
        found = prose(message)
        if found is not None:
            role, text = found
            messages.append({"from": role, "text": text})
    return {
        "title": body.get("title"),
        "total_messages": body.get("total_messages", len(stored)),
        "messages": messages,
        "earlier": body.get("next_cursor"),
    }


def prose(message: Any) -> tuple[str, str] | None:
    """``(who, text)`` for what the user typed or Lemma wrote; None for tool calls, tool results,
    thinking and retries, as Lemma's own search skips them."""
    if not isinstance(message, dict):
        return None
    kind = _PROSE_PARTS.get(message.get("kind"))
    parts = message.get("parts")
    if kind is None or not isinstance(parts, list):
        return None
    part_kind, role = kind
    texts = [
        _content(part)
        for part in parts
        if isinstance(part, dict) and part.get("part_kind") == part_kind
    ]
    text = "\n".join(t for t in texts if t).strip()
    if not text:
        return None
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n[... {len(text) - MAX_TEXT_CHARS} more characters]"
    return role, text


def _content(part: dict) -> str:
    content = part.get("content")
    if isinstance(content, list):
        content = "\n".join(item for item in content if isinstance(item, str))
    if not isinstance(content, str):
        return ""
    if content.startswith("{"):
        try:
            data = json.loads(content)
        except ValueError:
            return content
        if isinstance(data, dict) and isinstance(data.get("message"), str):
            return data["message"]
    return content


def _marked(snippet: str | None) -> str | None:
    if snippet is None:
        return None
    return snippet.replace(MATCH_START, "«").replace(MATCH_END, "»")


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    owner = item.get("owner")
    return {
        "id": item["id"],
        "title": item.get("title"),
        "last_message_at": item.get("last_message_at"),
        "created_at": item.get("created_at"),
        "files": [f.get("name") for f in item.get("files") or [] if isinstance(f, dict)],
        "run_active": bool(item.get("run_active")),
        "owner": owner.get("email") if isinstance(owner, dict) else None,
    }
