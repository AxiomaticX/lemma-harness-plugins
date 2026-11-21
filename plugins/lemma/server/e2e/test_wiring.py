"""The server lists the expected tools, and the wake hook fires on the right ones."""

import json
import re
from pathlib import Path

import pytest
from mcp import Client
from plugin_files import WAKE_HOOK, clean_copy, run_wake_hook, server_params, tool_name

from lemma_mcp import wake

TOOLS = {
    "create_conversation",
    "send_message",
    "answer_questions",
    "list_conversations",
    "find_conversations",
    "read_conversation",
    "list_options",
    "get_plan",
    "answer_plan",
    "review_task",
    "edit_plan",
    "delete_task",
    "reopen_task",
    "set_task_checks",
    "list_plan_revisions",
    "restore_plan_revision",
    "delete_plan",
    "list_workflows",
    "start_workflow",
    "run_plan",
    "wait_for_result",
    "get_result",
    "list_files",
    "download_file",
    "open_in_browser",
    "login",
    "logout",
}
RUN_STARTING = {
    "create_conversation",
    "start_workflow",
    "send_message",
    "answer_questions",
    "run_plan",
    "wait_for_result",
}


@pytest.fixture(scope="module")
def plugin_root(tmp_path_factory) -> Path:
    """The plugin in a clean copy of this checkout, with no .venv of its own yet."""
    return clean_copy(tmp_path_factory.mktemp("checkout"))


async def test_the_server_started_from_mcp_json_lists_the_tools(plugin_root, tmp_path):
    async with Client(server_params(plugin_root, tmp_path)) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}

    assert listed == TOOLS


def test_the_wake_hook_matches_exactly_the_tools_that_start_or_wait_on_a_run():
    # re.search, not fullmatch: an unanchored matcher also catches longer names.
    matched = {tool for tool in TOOLS if re.search(WAKE_HOOK["matcher"], tool_name(tool))}

    assert matched == RUN_STARTING


def _event(tool: str, tool_input: dict, result: dict) -> dict:
    """A PostToolUse event as Claude Code sends it for an MCP tool: the result as text blocks."""
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name(tool),
        "tool_input": tool_input,
        "tool_response": [{"type": "text", "text": json.dumps(result)}],
    }


def test_the_wake_hook_follows_a_run_claude_started_and_wakes_claude(plugin_root, tmp_path):
    started = {"conversation_id": "c1", "run_id": "r1", "url": "https://lemma.test/c1"}
    event = _event("create_conversation", {"content": "go", "mode": "act"}, started)

    done = run_wake_hook(event, plugin_root, tmp_path)

    # With no token it can't follow the run, so it wakes Claude at once to say why.
    assert done.returncode == wake.WAKE_CLAUDE, done.stderr
    assert done.stdout.startswith("Stopped waiting for Lemma run r1 in conversation c1:"), done


def test_the_wake_hook_stays_quiet_when_the_run_already_ended(plugin_root, tmp_path):
    ended = {"outcome": "answered", "answer": "42", "questions": [], "url": "https://lemma.test"}
    event = _event("wait_for_result", {"conversation_id": "c1", "run_id": "r1"}, ended)

    done = run_wake_hook(event, plugin_root, tmp_path)

    assert (done.returncode, done.stdout) == (0, ""), done.stderr
