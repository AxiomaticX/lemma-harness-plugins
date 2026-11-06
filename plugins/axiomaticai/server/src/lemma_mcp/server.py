"""The Lemma MCP tools: hand work to Lemma, wait for it, and bring the results back."""

import functools
import os
import uuid
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .auth import Session
from .client import LemmaClient, runs
from .client import files as remote_files
from .config import TARGET, Target
from .errors import LemmaError

MAX_WAIT_SECONDS = 600
WAKE_AFTER_MINUTES = 60

INSTRUCTIONS = (
    "Lemma is Axiomatic's research and engineering agent. Send it a task with send_message. "
    "Runs take minutes to hours; you are woken when the run ends, so carry on meanwhile."
)
SEND_MESSAGE = (
    "Send a message to Lemma, starting a new conversation unless conversation_id is given. "
    "files are local file paths, uploaded and added to the conversation first. machine applies "
    "to a new conversation only. Returns at once with the run id. You are woken when the run "
    "ends, or after wake_after_minutes (default 60) with word that it is still running; set it "
    "higher only when you know the run will take hours."
)
WAIT_FOR_RESULT = (
    "Wait up to timeout_s seconds (at most 600) for a run to finish, then report it. outcome is "
    "running (still going), answered (answer holds the reply), waiting_for_input (Lemma needs "
    "the user: give them url), or no_answer (the run ended without a reply: give the user url). "
    "If it is still running, you are woken when it ends or after wake_after_minutes, as for "
    "send_message; pass timeout_s=0 to only arm that."
)
DOWNLOAD_FILE = (
    "Save one of the conversation's files, by name or id, into a local directory. An existing "
    "file is never overwritten; the saved path is returned."
)


@dataclass
class App:
    target: Target
    client: LemmaClient
    project_dir: Path
    open_browser: bool

    @classmethod
    def from_env(cls) -> "App":
        data_dir = Path(os.environ.get("LEMMA_DATA_DIR") or Path.home() / ".lemma-mcp")
        return cls(
            target=TARGET,
            client=LemmaClient(Session(TARGET, data_dir)),
            project_dir=Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()),
            open_browser=os.environ.get("LEMMA_OPEN_BROWSER", "").lower() != "false",
        )

    def local_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else self.project_dir / path


def _reported[**P, R](tool: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Lemma failures come back as their own message rather than a bare tool error."""

    @functools.wraps(tool)
    async def call(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await tool(*args, **kwargs)
        except LemmaError as e:
            raise ToolError(str(e)) from e
        except httpx.HTTPError as e:
            raise ToolError(f"Could not reach Lemma: {e}") from e

    return call


def build_server(app: App) -> MCPServer:
    server = MCPServer("lemma", instructions=INSTRUCTIONS)

    def outcome(conversation_id: str, ended: runs.RunResult) -> dict[str, Any]:
        return {
            "outcome": ended.outcome,
            "answer": ended.answer,
            "url": app.target.conversation_url(conversation_id),
        }

    @server.tool(description=SEND_MESSAGE)
    @_reported
    async def send_message(
        content: str,
        conversation_id: str | None = None,
        files: list[str] | None = None,
        model: Literal["normal", "pro", "pro_fast"] | None = None,
        plan_mode: bool = False,
        machine: Literal["standard", "enhanced", "high_performance", "max", "gpu"] | None = None,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        is_new = conversation_id is None
        conversation_id = conversation_id or str(uuid.uuid4())
        paths = [app.local_path(p) for p in files or []]
        file_ids = await remote_files.upload(app.client, paths) if paths else []
        options: dict[str, Any] = {"plan_mode": plan_mode}
        if model is not None:
            options["model"] = model
        if machine is not None:
            options["sandbox_type"] = machine
        run_id = await runs.send(app.client, conversation_id, content, file_ids, options)
        url = app.target.conversation_url(conversation_id)
        if app.open_browser and is_new:
            webbrowser.open(url)
        return {"conversation_id": conversation_id, "run_id": run_id, "url": url}

    @server.tool(description=WAIT_FOR_RESULT)
    @_reported
    async def wait_for_result(
        conversation_id: str,
        run_id: str,
        timeout_s: int = MAX_WAIT_SECONDS,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        timeout = max(0, min(timeout_s, MAX_WAIT_SECONDS))
        return outcome(
            conversation_id, await runs.wait(app.client, conversation_id, run_id, timeout)
        )

    @server.tool()
    @_reported
    async def get_result(conversation_id: str, run_id: str) -> dict[str, Any]:
        """Report a run's outcome now, without waiting. Outcomes are as for wait_for_result."""
        return outcome(conversation_id, await runs.result(app.client, conversation_id, run_id))

    @server.tool()
    @_reported
    async def list_files(conversation_id: str) -> list[dict[str, Any]]:
        """The files in a conversation, including those Lemma produced."""
        return [
            {"id": f.id, "name": f.name, "ready": bool(f.download_url)}
            for f in await remote_files.list_files(app.client, conversation_id)
        ]

    @server.tool(description=DOWNLOAD_FILE)
    @_reported
    async def download_file(conversation_id: str, name: str, dest_dir: str) -> dict[str, str]:
        saved = await remote_files.download(
            app.client, conversation_id, name, app.local_path(dest_dir)
        )
        return {"path": str(saved)}

    @server.tool()
    @_reported
    async def login() -> str:
        """Sign in to Lemma in the browser. Other tools do this on first use."""
        await app.client.session.refresh()
        return f"Signed in to Lemma ({app.target.name})."

    @server.tool()
    @_reported
    async def logout() -> str:
        """Sign out of Lemma on this machine."""
        await app.client.session.logout()
        return f"Signed out of Lemma ({app.target.name})."

    return server


def main() -> None:
    build_server(App.from_env()).run()
