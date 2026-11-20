"""The Lemma MCP tools: hand work to Lemma, wait for it, and bring the results back."""

import functools
import inspect
import json
import os
import uuid
import webbrowser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .auth import Session
from .client import LemmaClient, conversations, options, plan, runs
from .client import files as remote_files
from .config import Target, target
from .errors import LemmaError

MAX_WAIT_SECONDS = 600
WAKE_AFTER_MINUTES = 60
DEFAULT_MAX_OUTPUT_CHARS = 40_000
CUT_OUTPUT = (
    "[Output cut at {cap} of {total} characters. To get the rest, call this tool again with the "
    "same arguments and output_file set to a local path; the whole output is saved there, never "
    "over an existing file.]"
)
CUT_CHANGE = (
    "[Output cut at {cap} of {total} characters. The change is made: do not call this tool again. "
    "To get the whole result, call {reread} with output_file set to a local path; it is saved "
    "there, never over an existing file.]"
)

INSTRUCTIONS = (
    "Lemma is Axiomatic's research and engineering agent. Start a conversation with "
    "create_conversation, and continue it with send_message. Runs take minutes to hours; you "
    "are woken when a run ends, so carry on meanwhile with other work. Do not answer a question "
    "you handed to Lemma yourself; report Lemma's answer when the run ends. Find an earlier "
    "conversation with find_conversations, and read it with read_conversation before you "
    "continue it."
)
WAKE = (
    "You are woken when the run ends, or after wake_after_minutes (default 60) with word that it "
    "is still running; set it higher only when you know the run will take hours."
)
CREATE_CONVERSATION = (
    "Start a new Lemma conversation with its first message. mode is act (work straight away) or "
    "plan (draft a plan for the user to approve first). model is the tier and provider who runs "
    "it; list_options shows the tiers the user has and the ones each provider runs. machine is "
    "the computer it runs on, fixed for the whole conversation. Whatever is left out comes from "
    "the user's defaults. files are local file paths, uploaded "
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
    "Answer what a run stopped on: one entry per question, each with the question's id, approved "
    "true or false, and a reason. Only answer as the user decided. The conversation goes on in a "
    "new run, whose id comes back. " + WAKE
)
GET_PLAN = (
    "Read a plan-mode conversation's plan: its revision, its tasks with their dependencies and "
    "checks, the questions it asks with their default answers, and the finished tasks waiting "
    "for the user's review."
)
EDIT_PLAN = (
    "Replace a plan's overview and tasks with the user's edit. Pass the revision get_plan "
    "returned; if the plan has changed since, the edit is refused, so read it again. tasks is "
    "the whole list: a task with its id is changed and keeps its answers and progress, one "
    "without an id is added, and one left out is removed. depends_on takes task ids, or numbers "
    "counting from 1 in this list. validation and verification take checks as get_plan shows "
    "them. The edited plan needs approving again. Only edit as the user decided."
)
DELETE_TASK = (
    "Delete a task from the plan, and the tasks that depend on it unless keep_dependents is "
    "true. Only as the user decided."
)
REOPEN_TASK = (
    "Reopen a task and every task that depends on it, discarding their results, so the next "
    "run_plan does them again. Only as the user decided."
)
SET_TASK_CHECKS = (
    "Turn a task's checks off (enabled false) so it runs without them and its result is "
    "unverified, or back on. Only as the user decided."
)
RESTORE_PLAN_REVISION = (
    "Make an earlier revision (see list_plan_revisions) the plan again. It needs approving "
    "again. Only as the user decided."
)
ANSWER_PLAN = (
    "Answer the plan's questions, as a map of question id to answer, and with approve true "
    "approve the plan as answered. Answering puts an approved plan back to draft, so it needs "
    "approve true again before it runs. Only answer and approve as the user decided."
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


class Answer(TypedDict):
    id: str
    approved: bool
    reason: NotRequired[str]


class PlanTask(TypedDict):
    id: NotRequired[str]
    name: str
    description: str
    depends_on: NotRequired[list[str]]
    validation: NotRequired[list[dict[str, Any]]]
    verification: NotRequired[list[dict[str, Any]]]
    evidence: NotRequired[list[dict[str, Any]]]


Mode = Literal["act", "plan"]
Provider = Literal["anthropic", "google", "open"]
Model = Literal["normal", "pro", "pro_fast"]
Machine = Literal["standard", "enhanced", "high_performance", "max", "gpu"]
DOWNLOAD_FILE = (
    "Save one of the conversation's files, by name or id, into a local directory. An existing "
    "file is never overwritten; the saved path is returned."
)
FIND_CONVERSATIONS = (
    "Search the user's Lemma conversations by the words in their titles, file names and "
    "messages, best match first. Search with the distinctive words the user used to describe the "
    "conversation. Each hit has the snippet that matched, when a message did; busy means a run is "
    "going in it now. The query is 2 to 200 characters. An empty list means the search found "
    "nothing; some accounts are searched only across their most recent conversations."
)
READ_CONVERSATION = (
    "Read what the user wrote and Lemma replied in a conversation, a page of limit messages "
    "(1 to 100) at a time. order latest counts index from the newest message and returns the "
    "page newest first; order oldest counts from the first and returns it oldest first. total is "
    "how many messages the conversation holds; index runs from 0 to total - 1."
)
MAX_READ_MESSAGES = 100


PROVIDER_TIERS: dict[str, tuple[str, ...]] = {
    "anthropic": ("pro_fast", "pro", "normal"),
    "google": ("pro", "normal"),
    "open": ("pro", "normal"),
}
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


def _max_output_chars(raw: str | None) -> int:
    """The output cap setting, or the default when it is unset or not a positive number."""
    try:
        chars = int(float(raw or ""))
    except ValueError:
        return DEFAULT_MAX_OUTPUT_CHARS
    return chars if chars > 0 else DEFAULT_MAX_OUTPUT_CHARS


@dataclass
class App:
    target: Target
    client: LemmaClient
    project_dir: Path
    open_browser: bool
    default_model: tuple[str, str] | None = None
    default_machine: str | None = None
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS

    @classmethod
    def from_env(cls) -> "App":
        data_dir = Path(os.environ.get("LEMMA_DATA_DIR") or Path.home() / ".lemma-mcp")
        lemma = target(os.environ.get("LEMMA_ENVIRONMENT"))
        return cls(
            target=lemma,
            client=LemmaClient(Session(lemma, data_dir)),
            project_dir=Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()),
            open_browser=os.environ.get("LEMMA_OPEN_BROWSER", "").lower() != "false",
            default_model=MODEL_CHOICES.get(os.environ.get("LEMMA_DEFAULT_MODEL", "")),
            default_machine=MACHINE_CHOICES.get(os.environ.get("LEMMA_DEFAULT_MACHINE", "")),
            max_output_chars=_max_output_chars(os.environ.get("LEMMA_MAX_TOOL_OUTPUT_CHARS")),
        )

    def starting(
        self, model: str | None, provider: str | None, machine: str | None
    ) -> dict[str, Any]:
        """A new conversation's model and machine: what Claude named, else the user's defaults."""
        if self.default_model is not None:
            provider = provider or self.default_model[0]
            model = model or self.default_model[1]
        return {
            "model": model,
            "provider": provider,
            "sandbox_type": machine or self.default_machine,
        }

    def local_path(self, raw: str) -> Path:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else self.project_dir / path

    def fit(self, result: Any, output_file: str | None, reread: str | None = None) -> str:
        """``result`` as text, saved whole to ``output_file`` when one is given; otherwise cut at
        the output cap, with word of how to get the rest. A tool that changes something names the
        tool that reads its result again in ``reread``, so the change is never made twice."""
        text = (
            result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False)
        )
        if output_file is not None:
            return self._save(text, output_file)
        if len(text) <= self.max_output_chars:
            return text
        cap, total = self.max_output_chars, len(text)
        if reread is None:
            note = CUT_OUTPUT.format(cap=cap, total=total)
        else:
            note = CUT_CHANGE.format(cap=cap, total=total, reread=reread)
        return f"{text[:cap]}\n\n{note}"

    def _save(self, text: str, output_file: str) -> str:
        path = remote_files.free_path(self.local_path(output_file))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        except OSError as e:
            raise ToolError(f"Could not save the output to {path}: {e}") from e
        return f"The whole output, {len(text)} characters, is saved to {path}."


def build_server(app: App) -> MCPServer:
    server = MCPServer("lemma", instructions=INSTRUCTIONS)

    def tool(description: str | None = None, reread: str | None = None):
        """Register a tool whose output is held to the cap, with output_file for the overflow, and
        whose Lemma failures come back as their own message rather than a bare tool error."""

        def register(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[str]]:
            @functools.wraps(fn)
            async def call(*args: Any, output_file: str | None = None, **kwargs: Any) -> str:
                try:
                    result = await fn(*args, **kwargs)
                except LemmaError as e:
                    raise ToolError(str(e)) from e
                except httpx.HTTPError as e:
                    raise ToolError(f"Could not reach Lemma: {e}") from e
                return app.fit(result, output_file, reread)

            signature = inspect.signature(fn)
            output_file = inspect.Parameter(
                "output_file",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=str | None,
            )
            call.__signature__ = signature.replace(
                parameters=[*signature.parameters.values(), output_file], return_annotation=str
            )
            return server.tool(description=description, structured_output=False)(call)

        return register

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

    @tool(description=CREATE_CONVERSATION)
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

    @tool(description=SEND_MESSAGE)
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

    @tool(description=ANSWER_QUESTIONS)
    async def answer_questions(
        conversation_id: str,
        run_id: str,
        answers: list[Answer],
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        resumed = await runs.answer(app.client, conversation_id, run_id, list(map(dict, answers)))
        return started(conversation_id, resumed)

    @tool()
    async def list_options() -> dict[str, Any]:
        """The model tiers (empty: no choice), the tiers each provider runs, and the machines."""
        models = await options.models(app.client)
        tiers = [model["key"] for model in models]
        return {
            "models": models,
            "providers": {
                provider: [tier for tier in tiers if tier in runs_on]
                for provider, runs_on in PROVIDER_TIERS.items()
            },
            "machines": await options.machines(app.client),
        }

    @tool(description=GET_PLAN)
    async def get_plan(conversation_id: str) -> dict[str, Any]:
        return await plan.get(app.client, conversation_id)

    @tool(description=ANSWER_PLAN, reread="get_plan")
    async def answer_plan(
        conversation_id: str, answers: dict[str, str], approve: bool = False
    ) -> dict[str, Any]:
        return await plan.answer(app.client, conversation_id, answers, approve)

    @tool(description=REVIEW_TASK, reread="get_plan")
    async def review_task(
        conversation_id: str,
        task_id: str,
        decision: Literal["approve", "disapprove", "waive"],
        reason: str = "",
    ) -> dict[str, Any]:
        return await plan.review(app.client, conversation_id, task_id, decision, reason)

    @tool(description=EDIT_PLAN, reread="get_plan")
    async def edit_plan(
        conversation_id: str, revision: int, overview: str, tasks: list[PlanTask]
    ) -> dict[str, Any]:
        return await plan.edit(
            app.client, conversation_id, revision, overview, list(map(dict, tasks))
        )

    @tool(description=DELETE_TASK, reread="get_plan")
    async def delete_task(
        conversation_id: str, task_id: str, keep_dependents: bool = False
    ) -> dict[str, Any]:
        return await plan.delete_task(app.client, conversation_id, task_id, keep_dependents)

    @tool(description=REOPEN_TASK, reread="get_plan")
    async def reopen_task(conversation_id: str, task_id: str) -> dict[str, Any]:
        return await plan.reopen_task(app.client, conversation_id, task_id)

    @tool(description=SET_TASK_CHECKS, reread="get_plan")
    async def set_task_checks(conversation_id: str, task_id: str, enabled: bool) -> dict[str, Any]:
        return await plan.set_task_checks(app.client, conversation_id, task_id, enabled)

    @tool()
    async def list_plan_revisions(conversation_id: str) -> list[dict[str, Any]]:
        """The plan's saved revisions, oldest first: who wrote each, and which were approved."""
        return await plan.revisions(app.client, conversation_id)

    @tool(description=RESTORE_PLAN_REVISION, reread="get_plan")
    async def restore_plan_revision(conversation_id: str, number: int) -> dict[str, Any]:
        return await plan.restore(app.client, conversation_id, number)

    @tool()
    async def delete_plan(conversation_id: str) -> str:
        """Delete a conversation's plan; the files its tasks produced stay. Only as the user
        decided."""
        await plan.delete(app.client, conversation_id)
        return "Deleted the plan."

    @tool()
    async def list_workflows() -> list[dict[str, Any]]:
        """Lemma's ready-made workflows, each with the inputs it asks for."""
        return await options.workflows(app.client)

    @tool(description=START_WORKFLOW)
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

    @tool(description=RUN_PLAN)
    async def run_plan(
        conversation_id: str,
        scope: Literal["next", "all"] = "all",
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        return started(conversation_id, await plan.run(app.client, conversation_id, scope))

    @tool(description=WAIT_FOR_RESULT)
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

    @tool()
    async def get_result(conversation_id: str, run_id: str) -> dict[str, Any]:
        """Report a run's outcome now, without waiting. Outcomes are as for wait_for_result."""
        return outcome(conversation_id, await runs.result(app.client, conversation_id, run_id))

    @tool()
    async def list_files(conversation_id: str) -> list[dict[str, Any]]:
        """The files in a conversation, including those Lemma produced. notebook marks a notebook,
        which opens in the browser (open_in_browser)."""
        listed = await remote_files.list_files(app.client, conversation_id)
        notebooks = await remote_files.notebooks(app.client, conversation_id)
        return [
            {
                "id": f.id,
                "name": f.name,
                "ready": bool(f.download_url),
                "notebook": f.name in notebooks,
            }
            for f in listed
        ]

    @tool(description=DOWNLOAD_FILE)
    async def download_file(conversation_id: str, name: str, dest_dir: str) -> dict[str, str]:
        saved = await remote_files.download(
            app.client, conversation_id, name, app.local_path(dest_dir)
        )
        return {"path": str(saved)}

    @tool(description=FIND_CONVERSATIONS)
    async def find_conversations(query: str) -> list[dict[str, Any]]:
        return [
            {**hit, "url": app.target.conversation_url(hit["conversation_id"])}
            for hit in await conversations.search(app.client, query)
        ]

    @tool(description=READ_CONVERSATION)
    async def read_conversation(
        conversation_id: str,
        limit: int = 10,
        index: int = 0,
        order: Literal["latest", "oldest"] = "latest",
    ) -> dict[str, Any]:
        limit = max(1, min(limit, MAX_READ_MESSAGES))
        return await conversations.transcript(
            app.client, conversation_id, limit, max(0, index), order
        )

    @tool()
    async def open_in_browser(conversation_id: str) -> dict[str, Any]:
        """Open a conversation in Lemma in the user's default browser. If opened is false, no
        browser could be opened: give the user url instead."""
        url = app.target.conversation_url(conversation_id)
        return {"opened": webbrowser.open(url), "url": url}

    @tool()
    async def login() -> str:
        """Sign in to Lemma in the browser. Other tools do this on first use."""
        await app.client.session.refresh()
        return f"Signed in to Lemma ({app.target.name})."

    @tool()
    async def logout() -> str:
        """Sign out of Lemma on this machine."""
        await app.client.session.logout()
        return f"Signed out of Lemma ({app.target.name})."

    return server


def main() -> None:
    build_server(App.from_env()).run()
