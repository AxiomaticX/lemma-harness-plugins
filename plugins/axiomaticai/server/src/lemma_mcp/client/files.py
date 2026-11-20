"""Sending files to a conversation, listing its files, and downloading them."""

import asyncio
import mimetypes
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..errors import LemmaError, NotFoundError
from . import LemmaClient

TRANSFER_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
CHUNK_BYTES = 1 << 20


@dataclass(frozen=True)
class RemoteFile:
    id: str
    name: str
    status: str | None
    download_url: str | None


async def upload(client: LemmaClient, paths: list[Path]) -> list[str]:
    """Upload local files for a message; returns their ids in order."""
    async with httpx.AsyncClient(timeout=TRANSFER_TIMEOUT) as storage:
        return [await _upload_one(client, storage, path) for path in paths]


async def _upload_one(client: LemmaClient, storage: httpx.AsyncClient, path: Path) -> str:
    if not path.is_file():
        raise LemmaError(f"{path} is not a file.")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    created = await client.request(
        "POST",
        "/files/",
        json={
            "file_name": path.name,
            "content_type": content_type,
            "size_bytes": path.stat().st_size,
        },
    )
    target = created.json()
    file_id = str(target["file_id"])
    try:
        stored = await storage.put(
            target["presigned_upload_url"],
            content=_chunks(path),
            headers={
                **target.get("upload_headers", {}),
                "Content-Type": content_type,
                "Content-Length": str(path.stat().st_size),
            },
        )
        stored.raise_for_status()
    except (OSError, httpx.HTTPError) as e:
        await client.request("POST", f"/files/{file_id}/confirmation", json={"status": "error"})
        raise LemmaError(f"Uploading {path.name} failed: {e}") from e
    await client.request("POST", f"/files/{file_id}/confirmation", json={"status": "uploaded"})
    return file_id


async def _chunks(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as source:
        while chunk := await asyncio.to_thread(source.read, CHUNK_BYTES):
            yield chunk


async def list_files(client: LemmaClient, conversation_id: str) -> list[RemoteFile]:
    response = await client.request(
        "GET", f"/conversations/{conversation_id}", params={"messages_limit": 1}
    )
    return [
        RemoteFile(
            id=str(f["id"]),
            name=f["name"],
            status=f.get("status"),
            download_url=f.get("download_url"),
        )
        for f in response.json().get("files") or []
    ]


async def notebooks(client: LemmaClient, conversation_id: str) -> set[str]:
    """The names of the conversation's files that are notebooks Lemma can open."""
    response = await client.request("GET", f"/conversations/{conversation_id}/notebooks")
    return set(response.json().get("files") or [])


async def download(client: LemmaClient, conversation_id: str, name: str, dest_dir: Path) -> Path:
    """Save the conversation's file named ``name`` (or with that id) into ``dest_dir``."""
    files = await list_files(client, conversation_id)
    matches = [f for f in files if name in (f.id, f.name)]
    if not matches:
        raise NotFoundError(f"The conversation has no file named {name}.")
    if len(matches) > 1:
        ids = ", ".join(f.id for f in matches)
        raise LemmaError(f"More than one file is named {name}; pass one of these ids: {ids}.")
    remote = matches[0]
    if not remote.download_url:
        raise LemmaError(f"{remote.name} is not ready to download yet.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = _free_path(dest_dir / Path(remote.name).name)
    partial = target.with_name(target.name + ".part")
    try:
        async with (
            httpx.AsyncClient(timeout=TRANSFER_TIMEOUT, follow_redirects=True) as storage,
            storage.stream("GET", remote.download_url) as response,
        ):
            response.raise_for_status()
            with partial.open("wb") as out:
                async for chunk in response.aiter_bytes():
                    out.write(chunk)
    except (OSError, httpx.HTTPError) as e:
        partial.unlink(missing_ok=True)
        raise LemmaError(f"Downloading {remote.name} failed: {e}") from e
    partial.rename(target)
    return target


def _free_path(path: Path) -> Path:
    """``path``, or ``name (n).ext`` when something is already there."""
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate
