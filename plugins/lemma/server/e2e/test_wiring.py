"""The server lists the expected tools, and the wake hook fires on the right ones."""

import re

from conftest import WAKE_HOOK, run_wake_hook, server_params, tool_name
from mcp import Client

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


async def test_the_server_started_from_mcp_json_lists_the_tools(tmp_path):
    async with Client(server_params(tmp_path)) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}

    assert listed == TOOLS


def test_the_wake_hook_matches_exactly_the_tools_that_start_or_wait_on_a_run():
    # re.search, not fullmatch: an unanchored matcher also catches longer names.
    matched = {tool for tool in TOOLS if re.search(WAKE_HOOK["matcher"], tool_name(tool))}

    assert matched == RUN_STARTING


def test_the_wake_hook_command_runs_and_stays_quiet_when_there_is_no_run_to_follow(tmp_path):
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name("wait_for_result"),
        "tool_input": {"conversation_id": "c1", "run_id": "r1"},
        "tool_response": {"outcome": "answered"},
    }

    done = run_wake_hook(event, tmp_path)

    assert (done.returncode, done.stdout) == (0, ""), done.stderr
