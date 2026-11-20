"""The Lemma MCP tools: hand work to Lemma, wait for it, and bring the results back."""

import functools
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
from .client import LemmaClient, options, plan, runs
from .client import files as remote_files
from .config import CONFIG_FILENAME, Target, load_settings, save_settings, target
from .errors import LemmaError

MAX_WAIT_SECONDS = 600
WAKE_AFTER_MINUTES = 60
MAX_WAKE_MINUTES = 23 * 60

INSTRUCTIONS = (
    "Lemma is Axiomatic's research and engineering agent. Start a conversation with "
    "create_conversation, and continue it with send_message. Runs take minutes to hours; you "
    "are woken when a run ends, so carry on meanwhile with other work. Do not answer a question "
    "you handed to Lemma yourself; report Lemma's answer when the run ends."
)
BACKGROUND_INSTRUCTIONS = (
    "Lemma is Axiomatic's research and engineering agent. Start a conversation with "
    "create_conversation, and continue it with send_message. Runs take minutes to hours; after "
    "starting a run, call wait_for_result so it waits in the background and wakes you when the "
    "run ends. Do not answer a question you handed to Lemma yourself; report Lemma's answer "
    "when the run ends."
)
WAKE = (
    "You are woken when the run ends, or after wake_after_minutes (default 60) with word that it "
    "is still running; set it higher only when you know the run will take hours."
)
BACKGROUND_WAKE = (
    "Call wait_for_result next with conversation_id and run_id; it runs in the background and "
    "wakes you when the run ends, or after wake_after_minutes (default 60) with outcome running."
)
CREATE_CONVERSATION = (
    "Start a new Lemma conversation with its first message. mode is act (work straight away) or "
    "plan (draft a plan for the user to approve first). model is the tier and provider who runs "
    "it; list_options shows the tiers the user has and the ones each provider runs. machine is "
    "the computer it runs on, fixed for the whole conversation. Whatever is left out comes from "
    "the user's defaults. files are local file paths (prefer absolute paths), uploaded "
    "into the conversation first. Returns at once with the run id. "
)
SEND_MESSAGE = (
    "Send the next message in a Lemma conversation. mode, model and provider change the "
    "conversation's own for this and later turns; leave them out to keep them. files are local "
    "file paths (prefer absolute paths), uploaded into the conversation first. Returns at once "
    "with the run id. "
)
WAIT_FOR_RESULT = (
    "Wait up to timeout_s seconds (at most 600) for a run to finish, then report it. outcome is "
    "running (still going), answered (answer holds the reply), waiting_for_input (questions "
    "holds what Lemma needs decided: ask the user, then answer_questions), or no_answer (the run "
    "ended without a reply: give the user url). If it is still running, you are woken when it "
    "ends or after wake_after_minutes, as for send_message; pass timeout_s=0 to only arm that."
)
BACKGROUND_WAIT_FOR_RESULT = (
    "Wait in the background for a run to finish (up to wake_after_minutes, default 60, or "
    "timeout_s seconds if set), then wake you with its outcome. outcome is running (still going: "
    "call wait_for_result again, with wake_after_minutes higher if it will take hours), answered "
    "(answer holds the reply), waiting_for_input (questions holds what Lemma needs decided: ask "
    "the user, then answer_questions), or no_answer (the run ended without a reply: give the "
    "user url)."
)
ANSWER_QUESTIONS = (
    "Answer what a run stopped on: one entry per question, each with the question's id, approved "
    "true or false, and a reason. Only answer as the user decided. The conversation goes on in a "
    "new run, whose id comes back. "
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
    "the user. Returns at once with the run id. "
)
START_WORKFLOW = (
    "Start a new Lemma conversation with one of its ready-made workflows (see list_workflows), "
    "giving its inputs as a map of input name to answer; a choice takes one of its options and "
    "a multi_choice a list of them. Its file inputs are the files given here, as local paths "
    "(prefer absolute paths). model, provider and machine are as for create_conversation. "
    "Returns at once with the run id. "
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
Environment = Literal["production", "staging", "dev"]
DefaultModel = Literal[
    "Lemma's default",
    "Anthropic · Pro Fast",
    "Anthropic · Pro",
    "Anthropic · Normal",
    "Google · Pro",
    "Google · Normal",
    "Open-weight · Pro",
    "Open-weight · Normal",
]
DefaultMachine = Literal["Standard", "Enhanced", "High performance", "Max", "GPU"]
DOWNLOAD_FILE = (
    "Save one of the conversation's files, by name or id, into a local directory (prefer an "
    "absolute path). An existing file is never overwritten; the saved path is returned."
)
CONFIGURE = (
    "Read or update the plugin's persistent settings (saved in config.json under the plugin "
    "data directory so they survive plugin updates). Call with no arguments to see the current "
    "settings; pass any subset of environment, open_browser, default_model and default_machine "
    "to change them immediately without restarting. Only change settings when the user asks."
)


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
_MODEL_LABELS: dict[tuple[str, str], str] = {v: k for k, v in MODEL_CHOICES.items()}
MACHINE_CHOICES: dict[str, str] = {
    "Standard": "standard",
    "Enhanced": "enhanced",
    "High performance": "high_performance",
    "Max": "max",
    "GPU": "gpu",
}
_MACHINE_LABELS: dict[str, str] = {v: k for k, v in MACHINE_CHOICES.items()}
_SETTING_ENV_VARS = (
    "LEMMA_ENVIRONMENT",
    "LEMMA_OPEN_BROWSER",
    "LEMMA_DEFAULT_MODEL",
    "LEMMA_DEFAULT_MACHINE",
)


def _parse_open_browser(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() != "false"


@dataclass
class App:
    target: Target
    client: LemmaClient
    project_dir: Path
    open_browser: bool
    default_model: tuple[str, str] | None = None
    default_machine: str | None = None
    background_wait: bool = False
    data_dir: Path | None = None

    @classmethod
    def from_env(cls) -> "App":
        data_dir = Path(
            os.environ.get("LEMMA_DATA_DIR")
            or os.environ.get("PLUGIN_DATA")
            or Path.home() / ".lemma-mcp"
        )
        saved = load_settings(data_dir)
        lemma = target(os.environ.get("LEMMA_ENVIRONMENT") or saved.get("environment"))
        raw_open = os.environ.get("LEMMA_OPEN_BROWSER")
        if raw_open:
            open_browser = _parse_open_browser(raw_open)
        elif "open_browser" in saved:
            open_browser = _parse_open_browser(saved["open_browser"])
        else:
            open_browser = True
        raw_model = os.environ.get("LEMMA_DEFAULT_MODEL") or saved.get("default_model") or ""
        raw_machine = os.environ.get("LEMMA_DEFAULT_MACHINE") or saved.get("default_machine") or ""
        harness = os.environ.get("LEMMA_HARNESS", "").strip().lower()
        return cls(
            target=lemma,
            client=LemmaClient(Session(lemma, data_dir)),
            project_dir=Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()),
            open_browser=open_browser,
            default_model=MODEL_CHOICES.get(raw_model),
            default_machine=MACHINE_CHOICES.get(raw_machine),
            background_wait=harness == "antigravity",
            data_dir=data_dir,
        )

    def settings(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "environment": self.target.name,
            "open_browser": self.open_browser,
            "default_model": _MODEL_LABELS.get(self.default_model, "Lemma's default")
            if self.default_model is not None
            else "Lemma's default",
            "default_machine": _MACHINE_LABELS.get(self.default_machine, "Standard")
            if self.default_machine is not None
            else "Standard",
            "config_path": str(self.data_dir / CONFIG_FILENAME) if self.data_dir else None,
        }
        overrides = [name for name in _SETTING_ENV_VARS if os.environ.get(name)]
        if overrides:
            info["env_overrides"] = overrides
        return info

    async def configure(
        self,
        *,
        environment: Environment | None = None,
        open_browser: bool | None = None,
        default_model: DefaultModel | None = None,
        default_machine: DefaultMachine | None = None,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if environment is not None:
            new_target = target(environment)
            updates["environment"] = new_target.name
            if new_target != self.target:
                self.target = new_target
                if self.data_dir is not None:
                    old_client = self.client
                    self.client = LemmaClient(Session(new_target, self.data_dir))
                    await old_client.aclose()
        if open_browser is not None:
            self.open_browser = open_browser
            updates["open_browser"] = open_browser
        if default_model is not None:
            self.default_model = MODEL_CHOICES.get(default_model)
            updates["default_model"] = default_model
        if default_machine is not None:
            self.default_machine = MACHINE_CHOICES.get(default_machine)
            updates["default_machine"] = default_machine
        if updates and self.data_dir is not None:
            save_settings(self.data_dir, updates)
        return self.settings()

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
    instructions = BACKGROUND_INSTRUCTIONS if app.background_wait else INSTRUCTIONS
    wake = BACKGROUND_WAKE if app.background_wait else WAKE
    wait_description = BACKGROUND_WAIT_FOR_RESULT if app.background_wait else WAIT_FOR_RESULT
    server = MCPServer("lemma", instructions=instructions)

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

    @server.tool(description=CREATE_CONVERSATION + wake)
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

    @server.tool(description=SEND_MESSAGE + wake)
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

    @server.tool(description=ANSWER_QUESTIONS + wake)
    @_reported
    async def answer_questions(
        conversation_id: str,
        run_id: str,
        answers: list[Answer],
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        resumed = await runs.answer(app.client, conversation_id, run_id, list(map(dict, answers)))
        return started(conversation_id, resumed)

    @server.tool()
    @_reported
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

    @server.tool(description=EDIT_PLAN)
    @_reported
    async def edit_plan(
        conversation_id: str, revision: int, overview: str, tasks: list[PlanTask]
    ) -> dict[str, Any]:
        return await plan.edit(
            app.client, conversation_id, revision, overview, list(map(dict, tasks))
        )

    @server.tool(description=DELETE_TASK)
    @_reported
    async def delete_task(
        conversation_id: str, task_id: str, keep_dependents: bool = False
    ) -> dict[str, Any]:
        return await plan.delete_task(app.client, conversation_id, task_id, keep_dependents)

    @server.tool(description=REOPEN_TASK)
    @_reported
    async def reopen_task(conversation_id: str, task_id: str) -> dict[str, Any]:
        return await plan.reopen_task(app.client, conversation_id, task_id)

    @server.tool(description=SET_TASK_CHECKS)
    @_reported
    async def set_task_checks(conversation_id: str, task_id: str, enabled: bool) -> dict[str, Any]:
        return await plan.set_task_checks(app.client, conversation_id, task_id, enabled)

    @server.tool()
    @_reported
    async def list_plan_revisions(conversation_id: str) -> list[dict[str, Any]]:
        """The plan's saved revisions, oldest first: who wrote each, and which were approved."""
        return await plan.revisions(app.client, conversation_id)

    @server.tool(description=RESTORE_PLAN_REVISION)
    @_reported
    async def restore_plan_revision(conversation_id: str, number: int) -> dict[str, Any]:
        return await plan.restore(app.client, conversation_id, number)

    @server.tool()
    @_reported
    async def delete_plan(conversation_id: str) -> str:
        """Delete a conversation's plan; the files its tasks produced stay. Only as the user
        decided."""
        await plan.delete(app.client, conversation_id)
        return "Deleted the plan."

    @server.tool()
    @_reported
    async def list_workflows() -> list[dict[str, Any]]:
        """Lemma's ready-made workflows, each with the inputs it asks for."""
        return await options.workflows(app.client)

    @server.tool(description=START_WORKFLOW + wake)
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

    @server.tool(description=RUN_PLAN + wake)
    @_reported
    async def run_plan(
        conversation_id: str,
        scope: Literal["next", "all"] = "all",
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        return started(conversation_id, await plan.run(app.client, conversation_id, scope))

    @server.tool(description=wait_description)
    @_reported
    async def wait_for_result(
        conversation_id: str,
        run_id: str,
        timeout_s: int | None = None,
        wake_after_minutes: int = WAKE_AFTER_MINUTES,
    ) -> dict[str, Any]:
        if app.background_wait:
            if timeout_s is not None:
                window = float(max(0, min(timeout_s, MAX_WAKE_MINUTES * 60)))
            else:
                minutes = max(1, min(wake_after_minutes, MAX_WAKE_MINUTES))
                window = float(minutes * 60)
            ended = await runs.wait_window(app.client, conversation_id, run_id, window)
            return outcome(conversation_id, ended)
        requested = MAX_WAIT_SECONDS if timeout_s is None else timeout_s
        timeout = max(0, min(requested, MAX_WAIT_SECONDS))
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

    @server.tool(description=CONFIGURE)
    @_reported
    async def configure(
        environment: Environment | None = None,
        open_browser: bool | None = None,
        default_model: DefaultModel | None = None,
        default_machine: DefaultMachine | None = None,
    ) -> dict[str, Any]:
        return await app.configure(
            environment=environment,
            open_browser=open_browser,
            default_model=default_model,
            default_machine=default_machine,
        )

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
