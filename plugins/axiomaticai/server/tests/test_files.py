import json
from pathlib import Path

import httpx
import pytest

from lemma_mcp.client import LemmaClient, files
from lemma_mcp.errors import LemmaError, NotFoundError

PUT_URL = "https://storage.test/upload?sig=x"
CONVERSATION = "https://api.test/conversations/c1"


def _conversation_files(*entries: dict) -> httpx.Response:
    return httpx.Response(200, json={"id": "c1", "files": list(entries)})


@pytest.fixture
def data_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.csv"
    path.write_text("x,y\n1,2\n")
    return path


SIZE_LIMIT = {"x-upload-check": "8"}


@pytest.fixture
def initiated(api):
    return api.post("https://api.test/files/").mock(
        return_value=httpx.Response(
            200,
            json={"file_id": "f1", "presigned_upload_url": PUT_URL, "upload_headers": SIZE_LIMIT},
        )
    )


async def test_an_upload_puts_the_bytes_to_storage_without_the_users_token(
    client: LemmaClient, api, data_file: Path, initiated
):
    put = api.put(PUT_URL).mock(return_value=httpx.Response(200))
    confirm = api.post("https://api.test/files/f1/confirmation").mock(
        return_value=httpx.Response(200)
    )

    assert await files.upload(client, [data_file]) == ["f1"]

    assert json.loads(initiated.calls.last.request.content) == {
        "file_name": "data.csv",
        "content_type": "text/csv",
        "size_bytes": 8,
    }
    stored = put.calls.last.request
    assert "Authorization" not in stored.headers
    assert stored.headers["Content-Type"] == "text/csv"
    assert stored.headers["x-upload-check"] == "8"
    assert stored.content == b"x,y\n1,2\n"
    assert json.loads(confirm.calls.last.request.content) == {"status": "uploaded"}


async def test_a_failed_upload_is_marked_failed(
    client: LemmaClient, api, data_file: Path, initiated
):
    api.put(PUT_URL).mock(return_value=httpx.Response(403))
    confirm = api.post("https://api.test/files/f1/confirmation").mock(
        return_value=httpx.Response(200)
    )

    with pytest.raises(LemmaError, match="Uploading data.csv failed"):
        await files.upload(client, [data_file])
    assert json.loads(confirm.calls.last.request.content) == {"status": "error"}


async def test_a_missing_local_file_is_refused_before_anything_is_sent(
    client: LemmaClient, api, tmp_path: Path, initiated
):
    with pytest.raises(LemmaError, match="is not a file"):
        await files.upload(client, [tmp_path / "nope.csv"])
    assert not initiated.called


async def test_a_download_streams_the_signed_link_without_the_users_token(
    client: LemmaClient, api, tmp_path: Path
):
    conversation = api.get(CONVERSATION).mock(
        return_value=_conversation_files(
            {"id": "f9", "name": "fit.png", "download_url": "https://storage.test/fit.png?sig"}
        )
    )
    fetched = api.get("https://storage.test/fit.png?sig").mock(
        return_value=httpx.Response(200, content=b"png-bytes")
    )
    (tmp_path / "fit.png").write_bytes(b"older")

    saved = await files.download(client, "c1", "fit.png", tmp_path)

    assert saved == tmp_path / "fit (1).png"
    assert saved.read_bytes() == b"png-bytes"
    assert (tmp_path / "fit.png").read_bytes() == b"older"
    assert "Authorization" not in fetched.calls.last.request.headers
    assert conversation.calls.last.request.url.params["messages_limit"] == "1"


async def test_a_file_name_cannot_write_outside_the_destination(
    client: LemmaClient, api, tmp_path: Path
):
    api.get(CONVERSATION).mock(
        return_value=_conversation_files(
            {"id": "f9", "name": "../../escape.txt", "download_url": "https://storage.test/e"}
        )
    )
    api.get("https://storage.test/e").mock(return_value=httpx.Response(200, content=b"x"))

    saved = await files.download(client, "c1", "f9", tmp_path / "out")

    assert saved == tmp_path / "out" / "escape.txt"


async def test_a_name_shared_by_two_files_asks_for_an_id(client: LemmaClient, api, tmp_path):
    api.get(CONVERSATION).mock(
        return_value=_conversation_files(
            {"id": "a", "name": "out.csv", "download_url": "u"},
            {"id": "b", "name": "out.csv", "download_url": "u"},
        )
    )

    with pytest.raises(LemmaError, match="pass one of these ids: a, b"):
        await files.download(client, "c1", "out.csv", tmp_path)


async def test_an_unknown_file_is_not_found(client: LemmaClient, api, tmp_path):
    api.get(CONVERSATION).mock(return_value=_conversation_files())

    with pytest.raises(NotFoundError):
        await files.download(client, "c1", "nothing.csv", tmp_path)
