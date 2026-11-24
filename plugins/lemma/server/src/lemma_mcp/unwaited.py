"""Lemma runs an Antigravity conversation started without a background wait on them yet, and the
Stop hook that keeps the agent from ending its turn until it starts one, since the wait is what
wakes it when the run ends."""

import json
import os
import re
import sys
from pathlib import Path

from .config import data_dir

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
CALLER_META_KEY = "antigravity.google/conversation_id"


def directory() -> Path:
    plugin_data = os.environ.get("PLUGIN_DATA")
    return (Path(plugin_data) if plugin_data else data_dir()) / "unwaited"


def _run_file(root: Path, caller: str, run_id: str) -> Path | None:
    if not (SAFE_ID.fullmatch(caller) and SAFE_ID.fullmatch(run_id)):
        return None
    return root / caller / f"{run_id}.json"


def record(root: Path, caller: str, conversation_id: str, run_id: str) -> None:
    path = _run_file(root, caller, run_id)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"conversation_id": conversation_id, "run_id": run_id}))


def clear(root: Path, caller: str, run_id: str) -> None:
    path = _run_file(root, caller, run_id)
    if path is not None:
        path.unlink(missing_ok=True)


def pending(root: Path, caller: str) -> list[dict[str, str]]:
    if not SAFE_ID.fullmatch(caller):
        return []
    found = []
    for path in sorted((root / caller).glob("*.json")):
        try:
            found.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return found


def stop_reason(runs: list[dict[str, str]]) -> str:
    calls = "; ".join(
        f"conversation_id {run['conversation_id']}, run_id {run['run_id']}" for run in runs
    )
    return (
        "A Lemma run you started is still going, and nothing will tell you when it ends. "
        f"Call wait_for_result now for each of these: {calls}. It waits in the background and "
        "wakes you when the run ends."
    )


def decide(event: dict, root: Path) -> dict[str, str]:
    """The Stop hook's answer: continue while a run has no wait on it, once per turn."""
    if event.get("continuationActive"):
        return {}
    runs = pending(root, str(event.get("conversationId") or ""))
    if not runs:
        return {}
    return {"decision": "continue", "reason": stop_reason(runs)}


def main() -> None:
    print(json.dumps(decide(json.load(sys.stdin), directory())), flush=True)
