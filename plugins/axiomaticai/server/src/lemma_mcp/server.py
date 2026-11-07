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
from .client import LemmaClient, options, plan, runs
from .client import files as remote_files
from .config import TARGET, Target
from .errors import LemmaError

MAX_WAIT_SECONDS = 600
WAKE_AFTER_MINUTES = 60

INSTRUCTIONS = (
    "Lemma is Axiomatic's research and engineering agent. Start a conversation with "
    "create_conversation, and continue it with send_message. Runs take minutes to hours; you "
    "are woken when a run ends, so carry on meanwhile."
)
WAKE = (
    "You are woken when the run ends, or after wake_after_minutes (default 60) with word that it "
    "is still running; set it higher only when you know the run will take hours."
)
CREATE_CONVERSATION = (
    "Start a new Lemma conversation with its first message. mode is act (work straight away) or "
    "plan (draft a plan for the user to approve first). model and provider choose the model "
    "(see list_options), and machine the computer it runs on, which is fixed for the whole "
    "conversation; leave them out for the user's defaults. files are local file paths, uploaded "
    "into the conversation first. Returns at once with the run id. " + WAKE
)
SEND_MESSAGE = (
    "Send the next message in a Lemma conversation. mode, model and provider change the "
    "conversation's own for this and later turns; leave them out to keep them. files are local "
    "file paths, uploaded into the conversation first. Returns at once with the run id. " + WAKE
)
WAIT_FOR_RESULT = (
    "Wait up to timeout_s seconds (at most 600) for a run to finish, then report it. outcome is "
    "running (still going), answered (answer holds the reply), waiting_for_input (questions "
    "holds what Lemma needs decided: ask the user, then answer_questions), or no_answer (the run "
    "ended without a reply: give the user url). If it is still running, you are woken when it "
    "ends or after wake_after_minutes, as for send_message; pass timeout_s=0 to only arm that."
)
ANSWER_QUESTIONS = (
    "Answer what a run stopped on: one entry per question id, with approved true or false and a "
    "reason. Only answer as the user decided. The conversation goes on in a new run, whose id "
    "comes back. " + WAKE
)
GET_PLAN = (
    "Read a plan-mode conversation's plan: its tasks, the questions it asks with their default "
    "answers, and the finished tasks waiting for the user's review."
)
ANSWER_PLAN = (
    "Answer the plan's questions, as a map of question id to answer, and with approve true "
    "approve the plan as answered. Only answer and approve as the user decided."
)
REVIEW_TASK = (
    "Decide a finished task that waits on review: approve, disapprove or waive, with a reason. "
    "Only decide as the user decided."
)
RUN_PLAN = (
    "Run an approved plan: scope next for its next task, or all for every task until one needs "
    "the user. Returns at once with the run id. " + WAKE
)
START_WORKFLOW = (
    "Start a new Lemma conversation with one of its ready-made workflows (see list_workflows), "
    "giving its inputs as a map of input name to answer; a choice takes one of its options and "
    "a multi_choice a list of them. Its file inputs are the files given here, as local paths. "
    "model, provider and machine are as for create_conversation. Returns at once with the run "
    "id. " + WAKE
)

Mode = Literal["act", "plan"]
Provider = Literal["anthropic", "google", "open"]
Model = Literal["normal", "pro", "pro_fast"]
Machine = Literal["standard", "enhanced", "high_performance", "max", "gpu"]
DOWNLOAD_FILE = (
    "Save one of the conversation's files, by name or id, into a local directory. An existing "
    "file is never overwritten; the saved path is returned."
)


MODEL_CHOICES: dict[str, tuple[str, str]] = {
    "Anthropic · Pro Fast": ("anthropic", "pro_fast"),
    "Anthropic · Pro": ("anthropic", "pro"),
    "Anthropic · Normal": ("anthropic", "normal"),
    "Google · Pro": ("google", "pro"),
    "Google · Normal": ("google", "normal"),
    "Open-weight · Pro": ("open", "pro"),
    "Open-weight · Normal": ("open", "normal"),
}
MACHINE_CHOICES: dict[str, str] = {
    "Standard": "standard",
    "Enhanced": "enhanced",
    "High performance": "high_performance",
    "Max": "max",
    "GPU": "gpu",
}


@dataclass
class App:
    target: Target
    client: LemmaClient
    project_dir: Path
    open_browser: bool
    default_model: tuple[str, str] | None = None
    default_machine: str | None = None

    @classmethod
    def from_env(cls) -> "App":
        data_dir = Path(os.environ.get("LEMMA_DATA_DIR") or Path.home() / ".lemma-mcp")
        return cls(
            target=TARGET,
            client=LemmaClient(Session(TARGET, data_dir)),
            project_dir=Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()),
            open_browser=os.environ.get("LEMMA_OPEN_BROWSER", "").lower() != "false",
            default_model=MODEL_CHOICES.get(os.environ.get("LEMMA_DEFAULT_MODEL", "")),
            default_machine=MACHINE_CHOICES.get(os.environ.get("LEMMA_DEFAULT_MACHINE", "")),
        )

    def starting(
        self, model: str | None, provider: str | None, machine: str | None
    ) -> dict[str, Any]:
        """A new conversation's model and machine: what Claude named, else the user's defaults."""
        if model is None and provider is None and self.default_model is not None:
            provider, model = self.default_model
        return {
            "model": model,
            "provider": provider,
            "sandbox_type": machine or self.default_machine,
        }

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
            "questions": list(ended.questions),
            "url": app.target.conversation_url(conversation_id),
        }

    def started(conversation_id: str, run_id: str) -> dict[str, Any]:
        url = app.target.conversation_url(conversation_id)
        return {"conversation_id": conversation_id, "run_id": run_id, "url": url}

    async def send(
        conversation_id: str,
        content: str | None,
        files: list[str] | None,
        settings: dict[str, Any],
    ) -> str:
        paths = [app.local_path(p) for p in files or []]
        file_ids = await remote_files.upload(app.client, paths) if paths else []
        chosen = {key: value for key, value in settings.items() if value is not None}
        return await runs.send(app.client, conversation_id, content, file_ids, chosen)

    @server.tool(description=CREATE_CONVERSATION)
    @_reported
    async def create_conversation(
        content: str,
        mode: Mode,
        model: Model | None = None,
        provider: Provider | None = None,
        machine: Machine | None = None,
        files: list[str] | None = None,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        run_id = await send(
            conversation_id,
            content,
            files,
            {"mode": mode, **app.starting(model, provider, machine)},
        )
        if app.open_browser:
            webbrowser.open(app.target.conversation_url(conversation_id))
        return started(conversation_id, run_id)

    @server.tool(description=SEND_MESSAGE)
    @_reported
    async def send_message(
        conversation_id: str,
        content: str,
        mode: Mode | None = None,
        model: Model | None = None,
        provider: Provider | None = None,
        files: list[str] | None = None,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        settings = {"mode": mode, "model": model, "provider": provider}
        return started(conversation_id, await send(conversation_id, content, files, settings))

    @server.tool(description=ANSWER_QUESTIONS)
    @_reported
    async def answer_questions(
        conversation_id: str,
        run_id: str,
        answers: list[dict[str, Any]],
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        resumed = await runs.answer(app.client, conversation_id, run_id, answers)
        return started(conversation_id, resumed)

    @server.tool()
    @_reported
    async def list_options() -> dict[str, Any]:
        """The model tiers (empty: no choice) and machines the user can pick for a conversation."""
        return {
            "models": await options.models(app.client),
            "machines": await options.machines(app.client),
        }

    @server.tool(description=GET_PLAN)
    @_reported
    async def get_plan(conversation_id: str) -> dict[str, Any]:
        return await plan.get(app.client, conversation_id)

    @server.tool(description=ANSWER_PLAN)
    @_reported
    async def answer_plan(
        conversation_id: str, answers: dict[str, str], approve: bool = False
    ) -> dict[str, Any]:
        return await plan.answer(app.client, conversation_id, answers, approve)

    @server.tool(description=REVIEW_TASK)
    @_reported
    async def review_task(
        conversation_id: str,
        task_id: str,
        decision: Literal["approve", "disapprove", "waive"],
        reason: str = "",
    ) -> dict[str, Any]:
        return await plan.review(app.client, conversation_id, task_id, decision, reason)

    @server.tool()
    @_reported
    async def list_workflows() -> list[dict[str, Any]]:
        """Lemma's ready-made workflows, each with the inputs it asks for."""
        return await options.workflows(app.client)

    @server.tool(description=START_WORKFLOW)
    @_reported
    async def start_workflow(
        name: str,
        inputs: dict[str, Any] | None = None,
        files: list[str] | None = None,
        model: Model | None = None,
        provider: Provider | None = None,
        machine: Machine | None = None,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        conversation_id = str(uuid.uuid4())
        settings = {
            "workflow": {"name": name, "inputs": inputs or {}},
            **app.starting(model, provider, machine),
        }
        run_id = await send(conversation_id, None, files, settings)
        if app.open_browser:
            webbrowser.open(app.target.conversation_url(conversation_id))
        return started(conversation_id, run_id)

    @server.tool(description=RUN_PLAN)
    @_reported
    async def run_plan(
        conversation_id: str,
        scope: Literal["next", "all"] = "all",
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        return started(conversation_id, await plan.run(app.client, conversation_id, scope))

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
    async def open_in_browser(conversation_id: str) -> dict[str, Any]:
        """Open a conversation in Lemma in the user's default browser. If opened is false, no
        browser could be opened: give the user url instead."""
        url = app.target.conversation_url(conversation_id)
        return {"opened": webbrowser.open(url), "url": url}

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
